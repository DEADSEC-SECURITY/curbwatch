from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3

from . import config


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    db = sqlite3.connect(config.DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(seed=True):
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, plate TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
            last_checked_at TEXT, last_success_at TEXT, last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY, ticket_number TEXT NOT NULL UNIQUE,
            car_id INTEGER NOT NULL REFERENCES cars(id), issued_at TEXT,
            time_source TEXT NOT NULL, description TEXT NOT NULL,
            location_name TEXT NOT NULL, location_id TEXT, street_key TEXT,
            fine_cents INTEGER NOT NULL, balance_cents INTEGER NOT NULL,
            surcharge_cents INTEGER NOT NULL, additional_fees_cents INTEGER NOT NULL DEFAULT 0,
            status_id INTEGER, status TEXT NOT NULL,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, raw_payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ticket_car ON tickets(car_id);
        CREATE INDEX IF NOT EXISTS ticket_time ON tickets(issued_at);
        CREATE TABLE IF NOT EXISTS ticket_changes (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            recorded_at TEXT NOT NULL, changes TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS check_runs (
            id TEXT PRIMARY KEY, status TEXT NOT NULL, car_id INTEGER REFERENCES cars(id),
            requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            total_cars INTEGER NOT NULL DEFAULT 0, completed_cars INTEGER NOT NULL DEFAULT 0,
            new_tickets INTEGER NOT NULL DEFAULT 0, updated_tickets INTEGER NOT NULL DEFAULT 0,
            errors TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plate_lookups (
            id TEXT PRIMARY KEY, plate TEXT NOT NULL, checked_at TEXT NOT NULL,
            tickets TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS map_shares (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, expires_at TEXT, revoked_at TEXT
        );
        """)
        from .auth import init_auth

        init_auth(db)
        from .notifications import init_notifications

        init_notifications(db)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(cars)")}
        for column in ("verification_status", "verified_at", "email", "plate_state"):
            if column not in columns:
                db.execute(f"ALTER TABLE cars ADD COLUMN {column} TEXT")
        if "record_type" not in columns:
            db.execute("ALTER TABLE cars ADD COLUMN record_type TEXT NOT NULL DEFAULT 'vehicle'")
        lookup_columns = {row["name"] for row in db.execute("PRAGMA table_info(plate_lookups)")}
        if "plate_state" not in lookup_columns:
            db.execute("ALTER TABLE plate_lookups ADD COLUMN plate_state TEXT")
        ticket_columns = {row["name"] for row in db.execute("PRAGMA table_info(tickets)")}
        if "additional_fees_cents" not in ticket_columns:
            from .portal import cents

            db.execute(
                "ALTER TABLE tickets ADD COLUMN additional_fees_cents INTEGER NOT NULL DEFAULT 0"
            )
            for row in db.execute("SELECT id,raw_payload FROM tickets").fetchall():
                raw = json.loads(row["raw_payload"])
                fees = sum(cents(item.get("amount")) for item in (raw.get("uplifts") or []))
                db.execute(
                    "UPDATE tickets SET additional_fees_cents=? WHERE id=?", (fees, row["id"])
                )
        if seed and not db.execute("SELECT 1 FROM app_meta WHERE key='seeded'").fetchone():
            db.executemany(
                "INSERT OR IGNORE INTO cars(name,plate,created_at) VALUES (?,?,?)",
                [(name, plate, now()) for name, plate in config.SEED_CARS],
            )
            db.execute("INSERT INTO app_meta VALUES ('seeded','true')")


def upsert_ticket(db, car_id, ticket):
    old = db.execute(
        "SELECT * FROM tickets WHERE ticket_number=?", (ticket["ticket_number"],)
    ).fetchone()
    if old and old["car_id"] != car_id:
        raise ValueError("The ticket is already associated with another monitored car")
    fields = list(ticket)
    timestamp = now()
    if old:
        changes = {
            key: {"before": old[key], "after": ticket[key]}
            for key in fields
            if key not in ("raw_payload",) and old[key] != ticket[key]
        }
        db.execute(
            f"UPDATE tickets SET {','.join(f'{key}=?' for key in fields)},last_seen_at=? WHERE id=?",
            [ticket[key] for key in fields] + [timestamp, old["id"]],
        )
        if changes:
            db.execute(
                "INSERT INTO ticket_changes(ticket_id,recorded_at,changes) VALUES (?,?,?)",
                (old["id"], timestamp, json.dumps(changes)),
            )
        return False, bool(changes)
    db.execute(
        f"INSERT INTO tickets ({','.join(fields)},car_id,first_seen_at,last_seen_at) "
        f"VALUES ({','.join('?' for _ in fields)},?,?,?)",
        [ticket[key] for key in fields] + [car_id, timestamp, timestamp],
    )
    return True, False
