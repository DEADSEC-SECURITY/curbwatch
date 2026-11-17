"""Transactional notification outbox and SMTP delivery, independent of ticket collection."""

from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime
import smtplib
import ssl
import time
from uuid import uuid4

from . import config
from .db import connect, now
from .email_templates import NY, monthly_email, new_ticket_email, test_email
from .mail_config import mail_settings, recipient_email, validate_delivery_settings

ERRORS = {
    "connection": "SMTP could not be reached. Delivery will retry.",
    "authentication": "SMTP sign-in failed. Check the username and password.",
    "tls": "A verified TLS connection could not be established.",
    "rejected": "The mail server rejected this sender, recipient or message.",
    "temporary": "The mail server temporarily refused delivery. Delivery will retry.",
    "uncertain": "The server handoff was interrupted. Check the recipient’s mailbox before resending.",
    "lease_expired": "Delivery stopped before its result was saved. Check the mailbox before resending.",
    "configuration": "Email configuration is unavailable or invalid. Review SMTP settings.",
    "cancelled": "The recipient or notification policy changed, or no outstanding tickets remain.",
}
TICKET_SELECT = """SELECT t.*,c.name AS car_name,c.plate,c.plate_state,c.email AS car_email,
                          c.last_success_at FROM tickets t JOIN cars c ON c.id=t.car_id"""


def init_notifications(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS email_outbox (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('ticket','monthly','test')),
        dedupe_key TEXT NOT NULL UNIQUE, recipient TEXT NOT NULL,
        ticket_id INTEGER REFERENCES tickets(id), report_month TEXT,
        status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','sending','sent','failed','uncertain','cancelled')),
        attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0,
        lease_until INTEGER, lock_token TEXT, created_at TEXT NOT NULL, sent_at TEXT,
        error_code TEXT, subject TEXT, message_id TEXT
      );
      CREATE INDEX IF NOT EXISTS email_pending ON email_outbox(status,next_attempt_at);
      CREATE TABLE IF NOT EXISTS email_report_runs (
        period TEXT PRIMARY KEY, generated_at TEXT NOT NULL, recipient_count INTEGER NOT NULL
      );
    """)


def insert_delivery(db, kind, key, recipient, ticket_id=None, period=None):
    delivery_id = uuid4().hex
    inserted = db.execute(
        """INSERT OR IGNORE INTO email_outbox
      (id,kind,dedupe_key,recipient,ticket_id,report_month,created_at) VALUES (?,?,?,?,?,?,?)""",
        (delivery_id, kind, key, recipient, ticket_id, period, now()),
    ).rowcount
    return delivery_id if inserted else None


def queue_ticket(db, ticket_id, settings):
    if not settings["enabled"] or not settings["ticket_alerts"]:
        return None
    ticket = db.execute(TICKET_SELECT + " WHERE t.id=?", (ticket_id,)).fetchone()
    recipient = recipient_email(ticket["car_email"]) if ticket else None
    if recipient:
        return insert_delivery(db, "ticket", f"ticket:{ticket_id}", recipient, ticket_id=ticket_id)


def notification_policy():
    try:
        settings, _, has_password = mail_settings()
        validate_delivery_settings(settings, has_password)
        return settings
    except Exception:
        # Broken mail configuration must never prevent authoritative ticket records being saved.
        return {"enabled": False, "ticket_alerts": False, "monthly_reports": False}


def queue_monthly_reports(at=None):
    at = (at or datetime.now(NY)).astimezone(NY)
    settings = notification_policy()
    if not settings["enabled"] or not settings["monthly_reports"]:
        return 0
    due = at.replace(
        day=settings["report_day"],
        hour=settings["report_hour"],
        minute=settings["report_minute"],
        second=0,
        microsecond=0,
    )
    if at < due:
        return 0
    period = at.strftime("%Y-%m")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM email_report_runs WHERE period=?", (period,)).fetchone():
            return 0
        rows = db.execute("""SELECT c.email FROM tickets t JOIN cars c ON c.id=t.car_id
                             WHERE t.balance_cents>0""").fetchall()
        recipients = sorted({email for row in rows if (email := recipient_email(row["email"]))})
        for recipient in recipients:
            insert_delivery(
                db, "monthly", f"monthly:{period}:{recipient}", recipient, period=period
            )
        db.execute("INSERT INTO email_report_runs VALUES (?,?,?)", (period, now(), len(recipients)))
        return len(recipients)


class DeliveryFailure(Exception):
    def __init__(self, code, retry=False, uncertain=False):
        super().__init__(code)
        self.code, self.retry, self.uncertain = code, retry, uncertain


def smtp_send(settings, message, recipient):
    client = None
    sending = False
    phase = "connection"
    try:
        context = ssl.create_default_context()
        if settings["security"] == "tls":
            client = smtplib.SMTP_SSL(
                settings["host"],
                settings["port"],
                timeout=config.SMTP_TIMEOUT_SECONDS,
                context=context,
            )
        else:
            client = smtplib.SMTP(
                settings["host"], settings["port"], timeout=config.SMTP_TIMEOUT_SECONDS
            )
            client.ehlo_or_helo_if_needed()
            if settings["security"] == "starttls":
                phase = "tls"
                client.starttls(context=context)  # Required; no fallback to plaintext.
                client.ehlo()
        if settings["username"]:
            phase = "authentication"
            client.login(settings["username"], settings["password"])
        sending = True
        phase = "send"
        refused = client.send_message(
            message, from_addr=settings["from_email"], to_addrs=[recipient]
        )
        if refused:
            raise DeliveryFailure("rejected")
    except DeliveryFailure:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise DeliveryFailure("authentication", retry=400 <= exc.smtp_code < 500) from None
    except ssl.SSLError:
        raise DeliveryFailure("tls") from None
    except smtplib.SMTPNotSupportedError:
        raise DeliveryFailure("tls" if phase == "tls" else "configuration") from None
    except smtplib.SMTPRecipientsRefused as exc:
        temporary = all(400 <= item[0] < 500 for item in exc.recipients.values())
        raise DeliveryFailure("temporary" if temporary else "rejected", retry=temporary) from None
    except smtplib.SMTPResponseException as exc:
        temporary = 400 <= exc.smtp_code < 500
        raise DeliveryFailure("temporary" if temporary else "rejected", retry=temporary) from None
    except (OSError, smtplib.SMTPException):
        raise DeliveryFailure(
            "uncertain" if sending else "connection", retry=not sending, uncertain=sending
        ) from None
    finally:
        if client:
            try:
                client.quit()
            except (OSError, smtplib.SMTPException):
                client.close()  # QUIT failure after successful DATA does not make delivery fail.


def build_delivery(row, settings, at):
    if row["kind"] == "test":
        return test_email(at)
    with connect() as db:
        if row["kind"] == "ticket":
            ticket = db.execute(TICKET_SELECT + " WHERE t.id=?", (row["ticket_id"],)).fetchone()
            if (
                not settings["ticket_alerts"]
                or not ticket
                or recipient_email(ticket["car_email"]) != row["recipient"]
            ):
                return None
            return new_ticket_email(dict(ticket), at)
        if not settings["monthly_reports"] or row["report_month"] != at.strftime("%Y-%m"):
            return None
        tickets = [
            dict(item)
            for item in db.execute(
                TICKET_SELECT + " WHERE t.balance_cents>0 ORDER BY c.id,t.issued_at,t.id"
            )
            if recipient_email(item["car_email"]) == row["recipient"]
        ]
        return monthly_email(tickets, row["report_month"], at) if tickets else None


def expire_sending_leases(db, timestamp):
    db.execute(
        "UPDATE email_outbox SET status='uncertain',error_code='lease_expired',lock_token=NULL "
        "WHERE status='sending' AND lease_until<=?",
        (timestamp,),
    )


def claim_delivery(timestamp):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_sending_leases(db, timestamp)
        row = db.execute(
            "SELECT * FROM email_outbox WHERE status='queued' AND next_attempt_at<=? ORDER BY created_at,id LIMIT 1",
            (timestamp,),
        ).fetchone()
        if not row:
            return None
        lock = uuid4().hex
        db.execute(
            "UPDATE email_outbox SET status='sending',attempts=attempts+1,lease_until=?,lock_token=? WHERE id=?",
            (timestamp + 300, lock, row["id"]),
        )
        return {**dict(row), "attempts": row["attempts"] + 1, "lock_token": lock}


def finish_delivery(row, status, *, error=None, retry_at=0):
    with connect() as db:
        db.execute(
            """UPDATE email_outbox SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,lock_token=NULL,
                   sent_at=? WHERE id=? AND status='sending' AND lock_token=?""",
            (
                status,
                error,
                retry_at,
                now() if status == "sent" else None,
                row["id"],
                row["lock_token"],
            ),
        )


def deliver_pending(limit=None, at=None):
    limit = config.EMAIL_BATCH_SIZE if limit is None else limit
    at = (at or datetime.now(NY)).astimezone(NY)
    with connect() as db:
        expire_sending_leases(db, int(time.time()))
    try:
        settings, _, has_password = mail_settings(secret=True)
        validate_delivery_settings(settings, has_password)
    except Exception:
        # Preserve queued records until configuration is fixed. Never log secret-bearing exceptions.
        with connect() as db:
            db.execute("UPDATE email_outbox SET error_code='configuration' WHERE status='queued'")
        return 0
    if not settings["enabled"]:
        return 0
    sent = 0
    for _ in range(limit):
        row = claim_delivery(int(time.time()))
        if row is None:
            break
        handoff_started = False
        try:
            # Re-read policy and credentials before every message, so disabling mail takes effect between deliveries.
            settings, _, has_password = mail_settings(secret=True)
            validate_delivery_settings(settings, has_password)
            if not settings["enabled"]:
                finish_delivery(row, "queued")
                break
            content = build_delivery(row, settings, at)
            if content is None:
                finish_delivery(row, "cancelled", error="cancelled")
                continue
            message = EmailMessage()
            message["From"] = Address(settings["from_name"], addr_spec=settings["from_email"])
            message["To"] = row["recipient"]
            message["Subject"] = " ".join(content.subject.splitlines())
            message["Date"] = format_datetime(at)
            message_id = (
                row["message_id"]
                or f"<curbwatch.{row['id']}@{settings['from_email'].split('@')[-1]}>"
            )
            message["Message-ID"] = message_id
            message["Auto-Submitted"] = "auto-generated"
            if settings["reply_to"]:
                message["Reply-To"] = settings["reply_to"]
            message.set_content(content.text)
            message.add_alternative(content.html, subtype="html")
            with connect() as db:
                db.execute(
                    "UPDATE email_outbox SET subject=?,message_id=? WHERE id=? AND lock_token=?",
                    (str(message["Subject"]), message_id, row["id"], row["lock_token"]),
                )
            handoff_started = True
            smtp_send(settings, message, row["recipient"])
            finish_delivery(row, "sent")
            sent += 1
        except DeliveryFailure as failure:
            retry = failure.retry and row["attempts"] < config.EMAIL_MAX_ATTEMPTS
            status = "uncertain" if failure.uncertain else "queued" if retry else "failed"
            backoff = (60, 300, 900, 3600, 10800)[min(row["attempts"] - 1, 4)]
            finish_delivery(
                row, status, error=failure.code, retry_at=int(time.time()) + backoff if retry else 0
            )
        except Exception:
            # An unexpected error after handoff may follow acceptance; never retry it automatically.
            finish_delivery(
                row,
                "uncertain" if handoff_started else "failed",
                error="uncertain" if handoff_started else "configuration",
            )
    return sent


def delivery_status():
    configuration_error = None
    try:
        settings, _, has_password = mail_settings(secret=True)
        validate_delivery_settings(settings, has_password)
    except Exception:
        configuration_error = ERRORS["configuration"]
    with connect() as db:
        counts = {
            row["status"]: row["count"]
            for row in db.execute(
                "SELECT status,COUNT(*) AS count FROM email_outbox GROUP BY status"
            )
        }
        recent = [
            {**dict(row), "error": ERRORS.get(row["error_code"])}
            for row in db.execute("""SELECT id,kind,recipient,status,attempts,created_at,sent_at,subject,error_code
                                         FROM email_outbox ORDER BY created_at DESC,id DESC LIMIT 12""")
        ]
        missing = sum(
            not recipient_email(row["email"]) for row in db.execute("SELECT email FROM cars")
        )
    return {
        "counts": counts,
        "recent": recent,
        "missing_recipient_vehicles": missing,
        "configuration_error": configuration_error,
    }
