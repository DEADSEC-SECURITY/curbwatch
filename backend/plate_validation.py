"""Short-lived ticket lookups, bound to the exact reviewed plate before saving."""

from datetime import datetime, timezone, timedelta
import json
import threading
import re
from uuid import uuid4

from . import config
from .db import connect, now
from .portal import normalize_ticket

LOOKUP_TTL = timedelta(seconds=config.LOOKUP_TTL_SECONDS)
lookup_lock = threading.Lock()


def preview_plate(plate, portal_factory, plate_state=None):
    with portal_factory() as portal:
        raw = portal.search(plate)
    if any(
        not re.sub(r"[^A-Z0-9]", "", str(ticket.get("plate_number") or "").upper())
        for ticket in raw
    ):
        from .portal import PortalError

        raise PortalError("The ticket response did not identify a license plate. Try again later.")
    tickets = [normalize_ticket(ticket, expected_plate=plate) for ticket in raw]
    lookup_id, checked_at = str(uuid4()), now()
    with connect() as db:
        db.execute(
            "DELETE FROM plate_lookups WHERE julianday(checked_at) < julianday('now','-10 minutes')"
        )
        db.execute(
            "INSERT INTO plate_lookups(id,plate,checked_at,tickets,plate_state) VALUES (?,?,?,?,?)",
            (lookup_id, plate, checked_at, json.dumps(tickets), plate_state),
        )
    return {
        "id": lookup_id,
        "plate": plate,
        "plate_state": plate_state,
        "checked_at": checked_at,
        "expires_at": (datetime.fromisoformat(checked_at) + LOOKUP_TTL).isoformat(),
        "outcome": "tickets_found" if tickets else "no_tickets",
        "ticket_count": len(tickets),
        "balance_cents": sum(ticket["balance_cents"] for ticket in tickets),
        "tickets": [
            {
                key: ticket[key]
                for key in (
                    "ticket_number",
                    "issued_at",
                    "location_name",
                    "description",
                    "status",
                    "balance_cents",
                )
            }
            for ticket in tickets
        ],
    }


def reviewed_lookup(db, lookup_id, plate, confirm_no_tickets, plate_state=None):
    lookup = db.execute("SELECT * FROM plate_lookups WHERE id=?", (lookup_id or "",)).fetchone()
    if not lookup or lookup["plate"] != plate:
        raise ValueError("Check this exact license plate for tickets before saving it.")
    if lookup["plate_state"] != plate_state:
        raise ValueError("The selected plate state changed. Check the plate again before saving.")
    age = datetime.now(timezone.utc) - datetime.fromisoformat(lookup["checked_at"])
    if age > LOOKUP_TTL:
        raise ValueError("This ticket check has expired. Check the plate again before saving.")
    tickets = json.loads(lookup["tickets"])
    if not tickets and not confirm_no_tickets:
        raise ValueError(
            "No tickets were found. Confirm that you checked the plate text before saving."
        )
    return lookup, tickets
