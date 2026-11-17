import json
import logging
import time
from uuid import uuid4

from . import config
from .db import connect, now, upsert_ticket
from .portal import SyracusePortal, normalize_ticket
from .notifications import notification_policy, queue_ticket

log = logging.getLogger(__name__)


def reserve_run(car_id=None):
    """Reserve globally before enqueueing, so repeated clicks cannot overlap checks."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # A killed process cannot keep the application locked forever.
        db.execute(
            "UPDATE check_runs SET status='failed',finished_at=?,errors=? "
            "WHERE status IN ('queued','running') AND julianday(requested_at) < julianday('now','-20 minutes')",
            (now(), json.dumps(["A previous check stopped before completing. Please try again."])),
        )
        existing = db.execute(
            "SELECT id FROM check_runs WHERE status IN ('queued','running') LIMIT 1"
        ).fetchone()
        if existing:
            return existing["id"], False
        run_id = str(uuid4())
        total = db.execute(
            "SELECT COUNT(*) FROM cars WHERE " + ("id=?" if car_id else "active=1"),
            (car_id,) if car_id else (),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO check_runs(id,status,car_id,requested_at,total_cars) VALUES (?,?,?,?,?)",
            (run_id, "queued", car_id, now(), total),
        )
        return run_id, True


def collect(run_id, portal_factory=SyracusePortal, delay=None):
    delay = config.COLLECTOR_DELAY_SECONDS if delay is None else delay
    with connect() as db:
        run = db.execute("SELECT * FROM check_runs WHERE id=?", (run_id,)).fetchone()
        if not run or run["status"] != "queued":
            return
        db.execute(
            "UPDATE check_runs SET status='running',started_at=? WHERE id=?", (now(), run_id)
        )
        cars = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM cars WHERE " + ("id=?" if run["car_id"] else "active=1"),
                (run["car_id"],) if run["car_id"] else (),
            )
        ]
    mail_policy = notification_policy()
    errors = []
    new_count = updated_count = completed = 0
    try:
        with portal_factory() as portal:
            for index, car in enumerate(cars):
                if index and delay:
                    time.sleep(delay)
                try:
                    # Validate the entire car result before writing any of its tickets.
                    tickets = [
                        normalize_ticket(raw, car["plate"]) for raw in portal.search(car["plate"])
                    ]
                    car_new = car_updated = 0
                    with connect() as db:
                        for ticket in tickets:
                            created, changed = upsert_ticket(db, car["id"], ticket)
                            if created:
                                ticket_id = db.execute(
                                    "SELECT id FROM tickets WHERE ticket_number=?",
                                    (ticket["ticket_number"],),
                                ).fetchone()[0]
                                queue_ticket(db, ticket_id, mail_policy)
                            car_new += int(created)
                            car_updated += int(changed)
                        db.execute(
                            "UPDATE cars SET last_checked_at=?,last_success_at=?,last_error=NULL WHERE id=?",
                            (now(), now(), car["id"]),
                        )
                    new_count += car_new
                    updated_count += car_updated
                except Exception as exc:
                    log.exception("A car check failed")
                    message = (
                        str(exc)
                        if isinstance(exc, (ValueError,)) or exc.__class__.__name__ == "PortalError"
                        else "Unable to process ticket data. Try again shortly."
                    )
                    errors.append(f"{car['plate']}: {message}")
                    with connect() as db:
                        db.execute(
                            "UPDATE cars SET last_checked_at=?,last_error=? WHERE id=?",
                            (now(), message, car["id"]),
                        )
                completed += 1
                with connect() as db:
                    db.execute(
                        "UPDATE check_runs SET completed_cars=?,new_tickets=?,updated_tickets=?,errors=? WHERE id=?",
                        (completed, new_count, updated_count, json.dumps(errors), run_id),
                    )
    except Exception:
        log.exception("Collector session failed")
        errors.append("Unable to start the ticket portal session. Try again shortly.")
    status = "completed" if not errors else ("partial" if completed > len(errors) else "failed")
    with connect() as db:
        db.execute(
            "UPDATE check_runs SET status=?,finished_at=?,errors=? WHERE id=?",
            (status, now(), json.dumps(errors), run_id),
        )


def enqueue(car_id=None):
    run_id, created = reserve_run(car_id)
    if created:
        try:
            from .tasks import check_tickets

            check_tickets.apply_async(args=[run_id], retry=False)
        except Exception as exc:
            with connect() as db:
                db.execute(
                    "UPDATE check_runs SET status='failed',finished_at=?,errors=? WHERE id=?",
                    (
                        now(),
                        json.dumps(
                            [
                                "The hourly checker is offline. Start the local services and try again."
                            ]
                        ),
                        run_id,
                    ),
                )
            raise RuntimeError(
                "The hourly checker is offline. Start the local services and try again."
            ) from exc
    return run_id, created
