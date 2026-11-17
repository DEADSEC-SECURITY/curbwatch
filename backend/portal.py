"""Read-only adapter for Syracuse's ticket search; no payment endpoints are used."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import html
import json
import re
import time
from urllib.parse import unquote, parse_qs
from zoneinfo import ZoneInfo

import httpx

from . import config
from .streets import street_key


class PortalError(Exception):
    pass


def cents(value):
    if isinstance(value, dict):
        value = value.get("$numberDecimal", value.get("$numberInt"))
    try:
        return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError, TypeError):
        raise PortalError("The portal returned an invalid monetary amount")


def issue_time(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, dict):
            value = value.get("$date", value)
            if isinstance(value, dict):
                value = value.get("$numberLong")
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(config.TIMEZONE))
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        raise PortalError("The portal returned an invalid issue date")


def normalize_ticket(raw, expected_plate=None):
    number = str(raw.get("ticket_number") or "").strip()
    if not number:
        raise PortalError("A ticket response is missing its ticket number")
    actual_plate = re.sub(r"[^A-Z0-9]", "", str(raw.get("plate_number") or "").upper())
    if expected_plate and actual_plate and actual_plate != expected_plate:
        raise PortalError("The portal returned a ticket for a different license plate")
    violations = raw.get("violations") or ([raw["violation"]] if raw.get("violation") else [])
    descriptions = [
        str(v.get("display_text") or (v.get("type") or {}).get("display_text") or "")
        for v in violations
    ]
    location = raw.get("location") or {}
    status_id = raw.get("tstatusid")
    status = {19: "Paid in full", 12: "Adjudication dismissed", 16: "Adjudication sustained"}.get(
        status_id
    )
    if status is None:
        status_object = raw.get("status") or {}
        supplied = (
            status_object.get("display_text") or status_object.get("description")
            if isinstance(status_object, dict)
            else str(status_object)
        )
        status = str(
            raw.get("tstatus")
            or supplied
            or (f"Status {status_id}" if status_id is not None else "Unknown")
        )
    address = str(location.get("description") or location.get("display_text") or "Unknown location")
    issued_at = issue_time(raw.get("issue_date"))
    return {
        "ticket_number": number,
        "issued_at": issued_at,
        "time_source": "ticket_issue_date" if issued_at else "unknown",
        "description": "; ".join(dict.fromkeys(d for d in descriptions if d))
        or "Parking violation",
        "location_name": address,
        "location_id": str(location.get("locationid") or ""),
        "street_key": street_key(address),
        "fine_cents": sum(cents(v.get("amount")) for v in violations),
        "balance_cents": cents(raw.get("balance")),
        "surcharge_cents": sum(cents(item.get("amount")) for item in (raw.get("surcharges") or [])),
        "additional_fees_cents": sum(
            cents(item.get("amount")) for item in (raw.get("uplifts") or [])
        ),
        "status_id": status_id,
        "status": status,
        "raw_payload": json.dumps(raw, separators=(",", ":")),
    }


class SyracusePortal:
    def __init__(self, base_url=None):
        self.base_url = (base_url or config.PORTAL_URL).rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=config.PORTAL_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "Curbwatch/0.1 (self-hosted ticket monitor)"},
        )
        self.token = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def session(self):
        response = self.client.get("/tickets/")
        response.raise_for_status()
        self.token = next(
            (unquote(c.value) for c in self.client.cookies.jar if c.name == "AW9_CSRF"), None
        )
        if not self.token:
            raise PortalError("The ticket portal did not provide a session token")

    def search(self, plate):
        for attempt in range(config.PORTAL_RETRIES):
            try:
                if self.token is None:
                    self.session()
                headers = {
                    "X-CSRF-Token": self.token,
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": self.base_url,
                    "Referer": self.base_url + "/tickets/",
                }
                response = self.client.post(
                    "/api/tickets/index.php",
                    params={"cmd": "search_tickets"},
                    files={
                        "ticket_plate_vin": (None, plate),
                        "formid": (None, "ticket_search_form"),
                    },
                    headers=headers,
                )
                if response.status_code in (401, 403, 419) and attempt < config.PORTAL_RETRIES - 1:
                    self.token = None
                    time.sleep(1)
                    continue
                response.raise_for_status()
                payload = self.payload(response)
                tickets = payload.get("tickets")
                if isinstance(tickets, list):
                    return tickets
                redirect = payload.get("data", "")
                if isinstance(redirect, str) and "redirect" in redirect:
                    query = parse_qs(
                        html.unescape(redirect).split("?", 1)[-1].split("'", 1)[0].split('"', 1)[0]
                    )
                    match = re.search(r"ticketid=([0-9]+)", html.unescape(redirect))
                    if match and query.get("cmd", ["detail"])[0] == "detail":
                        detail = self.client.get(
                            "/api/tickets/index.php",
                            params={"cmd": "get_ticket_detail", "ticketid": match[1]},
                            headers=headers,
                        )
                        detail.raise_for_status()
                        ticket = self.payload(detail).get("ticket")
                        if isinstance(ticket, dict):
                            return [ticket]
                # Only an explicit empty array/modal is an empty result. Error text
                # containing "no tickets found" must not authorize an unchecked save.
                raise PortalError("The ticket portal returned an unrecognized search response")
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if attempt < config.PORTAL_RETRIES - 1 and (
                    not isinstance(exc, httpx.HTTPStatusError)
                    or exc.response.status_code >= 500
                    or exc.response.status_code == 429
                ):
                    time.sleep(2**attempt)
                    continue
                raise PortalError(
                    f"Ticket portal unavailable ({type(exc).__name__}). Try again shortly."
                ) from exc
        raise PortalError("Unable to establish a ticket portal session")

    @staticmethod
    def payload(response):
        try:
            payload = response.json()
        except ValueError as exc:
            # The real portal sends this as text/javascript for exactly one result.
            text = response.text.strip()
            if re.match(r"^redirect\s*\(", text):
                return {"data": text.replace("\\/", "/")}
            if re.fullmatch(r"""\$\(["']#no_tickets_found["']\)\.modal\(\);?""", text):
                return {"tickets": []}
            raise PortalError("The ticket portal returned a page instead of ticket data") from exc
        if not isinstance(payload, dict):
            raise PortalError("The ticket portal returned an unexpected response")
        return payload
