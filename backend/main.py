from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import csv
import io
import json
import re
import sqlite3
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, EmailStr

from . import config
from .activity import activity, HistoryDays
from .collector import enqueue
from .db import connect, init_db, now, upsert_ticket
from .portal import cents, issue_time, normalize_ticket, PortalError, SyracusePortal
from .plate_validation import preview_plate, reviewed_lookup, lookup_lock
from .streets import street_data, street_key
from .sharing import owner_router
from .auth import (
    router as auth_router,
    bootstrap_admin,
    get_session,
    require_user,
    require_admin,
    base_url,
)
import hmac
from .plate_states import normalize_plate_state
from .email_api import router as email_router


@asynccontextmanager
async def lifespan(app):
    init_db()
    base_url()  # Fail closed on an invalid deployment origin.
    if config.AUTH_SESSION_HOURS < 1 or config.AUTH_SESSION_HOURS > 168:
        raise ValueError("PARKING_SESSION_HOURS must be between 1 and 168.")
    bootstrap_admin()
    yield


app = FastAPI(
    title="Parking Checker",
    version="0.1.0",
    lifespan=lifespan,
    description="Local vehicle tracking, read-only Syracuse ticket checks, and historical street activity.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Validation errors must not echo submitted passwords, invitation tokens or client secrets.
    return JSONResponse(
        {"detail": [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]},
        status_code=422,
    )


PUBLIC_AUTH = {
    "/api/health",
    "/api/auth/config",
    "/api/auth/login",
    "/api/auth/session",
    "/api/auth/invitations/accept",
    "/api/auth/oidc/start",
    "/api/auth/oidc/callback",
}


@app.middleware("http")
async def access_protection(request: Request, call_next):
    from fastapi.responses import JSONResponse

    path = request.url.path
    protected = (path.startswith("/api/") and path not in PUBLIC_AUTH) or path in (
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
    )
    response = None
    user = get_session(request) if path.startswith("/api/") or protected else None
    request.state.user = user
    if protected and not user:
        response = JSONResponse({"detail": "Sign in to continue."}, status_code=401)
    elif request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = {base_url(), *config.CORS_ORIGINS}
        # The actual origin also supports localhost aliases during local development only.
        if base_url().startswith("http://"):
            allowed.add(str(request.base_url).rstrip("/"))
        if origin and origin not in allowed:
            response = JSONResponse(
                {"detail": "This request must come from the app."}, status_code=403
            )
        elif path.startswith("/api/") and "application/json" not in request.headers.get(
            "content-type", ""
        ):
            response = JSONResponse({"detail": "Send JSON from the app."}, status_code=415)
        elif protected and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), user["csrf"]
        ):
            response = JSONResponse(
                {"detail": "Refresh the app before saving this change."}, status_code=403
            )
    if response is None:
        response = await call_next(request)
    if path.startswith("/api/") or protected:
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            }
        )
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    )
    return response


app.include_router(auth_router)
app.include_router(email_router)
app.include_router(owner_router, dependencies=[Depends(require_admin)])
# Document the same session requirement enforced by the middleware on all data routes.


class CarCreate(BaseModel):
    name: str = Field(default="", max_length=80)
    plate: str = Field(min_length=1, max_length=18)
    lookup_id: str | None = Field(default=None, max_length=64)
    confirm_no_tickets: bool = False
    email: EmailStr | None = None
    plate_state: str | None = Field(default=None, max_length=2)

    @field_validator("plate_state", mode="before")
    @classmethod
    def optional_plate_state(cls, value):
        return normalize_plate_state(value)

    @field_validator("email", mode="before")
    @classmethod
    def optional_email(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value):
        value = re.sub(r"[\s-]", "", value.upper())
        if not re.fullmatch(r"[A-Z0-9]{1,10}", value):
            raise ValueError("Enter 1–10 letters or numbers for the license plate")
        return value

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        return value.strip()


class CarUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    email: EmailStr | None = None
    plate_state: str | None = Field(default=None, max_length=2)

    @field_validator("plate_state", mode="before")
    @classmethod
    def optional_plate_state(cls, value):
        return normalize_plate_state(value)

    @field_validator("email", mode="before")
    @classmethod
    def optional_email(cls, value):
        return CarCreate.optional_email(value)


class PlateLookup(BaseModel):
    plate: str = Field(min_length=1, max_length=18)
    plate_state: str | None = Field(default=None, max_length=2)

    @field_validator("plate_state", mode="before")
    @classmethod
    def optional_plate_state(cls, value):
        return normalize_plate_state(value)

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value):
        return CarCreate.normalize_plate(value)


class CheckRequest(BaseModel):
    car_id: int | None = None


class ImportRequest(BaseModel):
    content: str = Field(max_length=5_000_000)
    format: str = Field(pattern="^(csv|json)$")
    car_id: int | None = None


def require_car(db, car_id):
    car = db.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()
    if not car:
        raise HTTPException(404, "Vehicle not found")
    return car


@app.get("/api/health")
def health():
    return {"status": "ok", "timezone": config.TIMEZONE}


@app.get("/api/cars", dependencies=[Depends(require_user)])
def cars():
    with connect() as db:
        return [
            dict(row)
            for row in db.execute("""
          SELECT c.*,COUNT(t.id) AS ticket_count,COALESCE(SUM(t.balance_cents),0) AS balance_cents,
                 COALESCE(SUM(t.fine_cents+t.surcharge_cents+t.additional_fees_cents),0) AS cost_cents,
                 COALESCE(SUM(CASE WHEN t.status_id=19 THEN t.fine_cents+t.surcharge_cents+t.additional_fees_cents ELSE 0 END),0) AS total_spent_cents,
                 SUM(CASE WHEN t.status_id=19 THEN 1 ELSE 0 END) AS paid_ticket_count
          FROM cars c LEFT JOIN tickets t ON t.car_id=c.id GROUP BY c.id ORDER BY c.id
        """)
        ]


@app.post("/api/cars", status_code=201, dependencies=[Depends(require_user)])
def create_car(body: CarCreate):
    try:
        with connect() as db:
            if db.execute("SELECT 1 FROM cars WHERE plate=?", (body.plate,)).fetchone():
                raise HTTPException(409, "This license plate is already being tracked")
            lookup, tickets = reviewed_lookup(
                db, body.lookup_id, body.plate, body.confirm_no_tickets, body.plate_state
            )
            status = "ticket_match" if tickets else "user_confirmed_no_tickets"
            row = db.execute(
                """INSERT INTO cars(name,plate,created_at,last_checked_at,last_success_at,
                             verification_status,verified_at,email,plate_state) VALUES (?,?,?,?,?,?,?,?,?) RETURNING *""",
                (
                    body.name or body.plate,
                    body.plate,
                    now(),
                    lookup["checked_at"],
                    lookup["checked_at"],
                    status,
                    lookup["checked_at"],
                    body.email,
                    body.plate_state,
                ),
            ).fetchone()
            for ticket in tickets:
                upsert_ticket(db, row["id"], ticket)
            db.execute("DELETE FROM plate_lookups WHERE id=?", (body.lookup_id,))
            return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "This license plate is already being tracked")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/plate-lookups", dependencies=[Depends(require_user)])
def lookup_plate(body: PlateLookup):
    with connect() as db:
        existing = db.execute("SELECT id FROM cars WHERE plate=?", (body.plate,)).fetchone()
        if existing:
            raise HTTPException(409, "This license plate is already being tracked")
    if not lookup_lock.acquire(blocking=False):
        raise HTTPException(429, "Another plate lookup is running. Please try again in a moment.")
    try:
        return preview_plate(body.plate, SyracusePortal, body.plate_state)
    except (PortalError, ValueError) as exc:
        raise HTTPException(503, f"Could not verify this plate: {exc}")
    finally:
        lookup_lock.release()


@app.patch("/api/cars/{car_id}", dependencies=[Depends(require_user)])
def update_car(car_id: int, body: CarUpdate):
    with connect() as db:
        require_car(db, car_id)
        updates = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if key in ("email", "plate_state") or value is not None
        }
        if "name" in updates:
            updates["name"] = updates["name"].strip()
            if not updates["name"]:
                raise HTTPException(422, "Give this vehicle a name")
        if updates:
            db.execute(
                f"UPDATE cars SET {','.join(f'{key}=?' for key in updates)} WHERE id=?",
                [*updates.values(), car_id],
            )
        return dict(require_car(db, car_id))


@app.get("/api/tickets", dependencies=[Depends(require_user)])
def tickets(
    car_id: int | None = None, search: str = "", limit: Annotated[int, Query(ge=1, le=5000)] = 1000
):
    clauses, params = [], []
    if car_id:
        clauses.append("t.car_id=?")
        params.append(car_id)
    if search:
        clauses.append(
            "(t.ticket_number LIKE ? OR t.location_name LIKE ? OR c.plate LIKE ? OR c.name LIKE ?)"
        )
        params.extend(["%" + search + "%"] * 4)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"""SELECT t.id,t.ticket_number,t.car_id,t.issued_at,t.time_source,t.description,
                t.location_name,t.street_key,t.fine_cents,t.balance_cents,t.surcharge_cents,t.additional_fees_cents,t.status,t.status_id,
                t.first_seen_at,t.last_seen_at,c.plate,c.plate_state,c.name AS car_name
                FROM tickets t JOIN cars c ON c.id=t.car_id {where}
                ORDER BY t.issued_at DESC,t.id DESC LIMIT ?""",
            params + [limit],
        )
        return [dict(row) for row in rows]


@app.get("/api/tickets/{ticket_id}/changes", dependencies=[Depends(require_user)])
def ticket_changes(ticket_id: int):
    with connect() as db:
        return [
            {**dict(row), "changes": json.loads(row["changes"])}
            for row in db.execute(
                "SELECT recorded_at,changes FROM ticket_changes WHERE ticket_id=? ORDER BY id DESC",
                (ticket_id,),
            )
        ]


@app.post("/api/checks", status_code=202, dependencies=[Depends(require_user)])
def create_check(body: CheckRequest):
    if body.car_id:
        with connect() as db:
            require_car(db, body.car_id)
    try:
        run_id, created = enqueue(body.car_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"id": run_id, "created": created}


@app.get("/api/checks", dependencies=[Depends(require_user)])
def checks():
    with connect() as db:
        return [
            {**dict(row), "errors": json.loads(row["errors"])}
            for row in db.execute("SELECT * FROM check_runs ORDER BY requested_at DESC LIMIT 20")
        ]


@app.get("/api/overview", dependencies=[Depends(require_user)])
def overview():
    with connect() as db:
        stats = dict(
            db.execute("""SELECT COUNT(*) AS tickets,COALESCE(SUM(balance_cents),0) AS balance_cents,
           COALESCE(SUM(CASE WHEN status_id=19 THEN fine_cents+surcharge_cents+additional_fees_cents ELSE 0 END),0) AS total_spent_cents,
           COUNT(DISTINCT street_key) AS streets,MIN(issued_at) AS oldest_ticket,MAX(issued_at) AS newest_ticket,
           SUM(CASE WHEN issued_at IS NULL THEN 1 ELSE 0 END) AS undated FROM tickets""").fetchone()
        )
        stats["cars"] = db.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
        stats["active_cars"] = db.execute("SELECT COUNT(*) FROM cars WHERE active=1").fetchone()[0]
        stats["last_success_at"] = db.execute("SELECT MAX(last_success_at) FROM cars").fetchone()[0]
        heartbeat = db.execute("SELECT value FROM app_meta WHERE key='worker_heartbeat'").fetchone()
        stats["hourly_checks_running"] = bool(
            heartbeat
            and (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat[0])).total_seconds()
            < 120
        )
        stats["timezone"] = config.TIMEZONE
        return stats


@app.get("/api/streets", dependencies=[Depends(require_user)])
def streets():
    return street_data()


@app.get("/api/activity", dependencies=[Depends(require_user)])
def get_activity(
    day: date | None = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    car_id: int | None = None,
    history_days: HistoryDays = config.DEFAULT_HISTORY_DAYS,
):
    current = datetime.now(ZoneInfo(config.TIMEZONE))
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM tickets" + (" WHERE car_id=?" if car_id else ""),
                (car_id,) if car_id else (),
            )
        ]
    return activity(
        rows, day or current.date(), hour if hour is not None else current.hour, history_days
    )


@app.post("/api/import", dependencies=[Depends(require_user)])
def import_history(body: ImportRequest):
    try:
        rows = (
            json.loads(body.content)
            if body.format == "json"
            else list(csv.DictReader(io.StringIO(body.content.lstrip("\ufeff"))))
        )
        if isinstance(rows, dict):
            rows = rows.get("tickets", rows.get("list", []))
        if not isinstance(rows, list) or not rows or len(rows) > 10000:
            raise ValueError("Choose a CSV or JSON file containing 1–10,000 ticket records")
        new = changed = 0
        with connect() as db:
            if body.car_id:
                require_car(db, body.car_id)
            for index, row in enumerate(rows, 1):
                if not isinstance(row, dict):
                    raise ValueError(f"Row {index} is not a ticket record")
                plate = re.sub(
                    r"[^A-Z0-9]",
                    "",
                    str(
                        row.get("License Plate")
                        or row.get("plate")
                        or row.get("plate_number")
                        or ""
                    ).upper(),
                )
                car = (
                    require_car(db, body.car_id)
                    if body.car_id
                    else db.execute("SELECT * FROM cars WHERE plate=?", (plate,)).fetchone()
                )
                if not car:
                    raise ValueError(
                        f"Row {index}: select a vehicle or provide its License Plate column"
                    )
                if plate and plate != car["plate"]:
                    raise ValueError(
                        f"Row {index}: license plate does not match the selected vehicle"
                    )
                if "ticket_number" in row and (
                    isinstance(row.get("violation"), dict)
                    or isinstance(row.get("violations"), list)
                ):
                    ticket = normalize_ticket(row, car["plate"])
                else:
                    number = str(row.get("Ticket Number") or row.get("ticket_number") or "").strip()
                    if not number:
                        raise ValueError(f"Row {index}: missing Ticket Number")
                    location = str(
                        row.get("Location Name") or row.get("location_name") or "Unknown location"
                    )
                    timestamp = issue_time(row.get("Issue Date") or row.get("issued_at"))
                    ticket = {
                        "ticket_number": number,
                        "issued_at": timestamp,
                        "time_source": "legacy_import_unverified" if timestamp else "unknown",
                        "description": str(row.get("Description") or "Parking violation"),
                        "location_name": location,
                        "location_id": str(row.get("Location Id") or ""),
                        "street_key": street_key(location),
                        "fine_cents": cents(row.get("Fine")),
                        "balance_cents": cents(row.get("Balance")),
                        "surcharge_cents": cents(row.get("Surcharge")),
                        "status_id": int(row["Status Id"]) if row.get("Status Id") else None,
                        "status": str(row.get("Status") or "Unknown"),
                        "raw_payload": json.dumps(row),
                    }
                # A legacy export must not overwrite more authoritative live portal data.
                existing = db.execute(
                    "SELECT time_source FROM tickets WHERE ticket_number=?",
                    (ticket["ticket_number"],),
                ).fetchone()
                if (
                    existing
                    and existing["time_source"] == "ticket_issue_date"
                    and ticket["time_source"] != "ticket_issue_date"
                ):
                    continue
                created, updated = upsert_ticket(db, car["id"], ticket)
                new += int(created)
                changed += int(updated)
        return {"new_tickets": new, "updated_tickets": changed}
    except (ValueError, PortalError) as exc:
        raise HTTPException(422, str(exc))


# A production build is served from the same local address as the API.
@app.get("/runtime-config.js", include_in_schema=False)
def runtime_config():
    from .runtime import public_config_script

    return Response(
        public_config_script(),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


dist = config.ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(dist / "favicon.svg")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(
            dist / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/")
    def index():
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=dist, html=True), name="pwa-files")
