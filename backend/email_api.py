from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr

from .auth import require_admin
from .db import connect
from .email_templates import NY, sample_tickets, monthly_email, new_ticket_email
from .mail_config import (
    MailSettings,
    mail_settings,
    public_mail_settings,
    recipient_email,
    save_mail_settings,
    validate_delivery_settings,
)
from .notifications import delivery_status, insert_delivery

router = APIRouter(prefix="/api/admin/email", dependencies=[Depends(require_admin)])


@router.get("")
def get_email_settings():
    return {"configuration": public_mail_settings(), **delivery_status()}


@router.put("")
def put_email_settings(body: MailSettings):
    if mail_settings()[1]:
        raise HTTPException(409, "SMTP is managed by deployment configuration.")
    try:
        save_mail_settings(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return get_email_settings()


class TestMail(BaseModel):
    recipient: EmailStr


@router.post("/test", status_code=202)
def queue_test(body: TestMail):
    settings, _, has_password = mail_settings()
    try:
        validate_delivery_settings(settings, has_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not settings["enabled"]:
        raise HTTPException(409, "Save and enable SMTP before sending a test email.")
    with connect() as db:
        delivery_id = insert_delivery(
            db, "test", "test:" + uuid4().hex, recipient_email(str(body.recipient))
        )
    return {"id": delivery_id, "status": "queued"}


@router.get("/preview", response_class=HTMLResponse)
def preview_email(kind: Literal["new_ticket", "monthly"] = "new_ticket"):
    at = datetime.now(NY)
    samples = sample_tickets(at)
    content = (
        new_ticket_email(samples[0], at)
        if kind == "new_ticket"
        else monthly_email(samples, at.strftime("%Y-%m"), at)
    )
    return HTMLResponse(content.html)


class RetryMail(BaseModel):
    acknowledge_uncertain: bool = False


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
def retry_delivery(delivery_id: str, body: RetryMail):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status FROM email_outbox WHERE id=?", (delivery_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Delivery not found.")
        if row["status"] not in ("failed", "uncertain"):
            raise HTTPException(409, "Only failed or unconfirmed deliveries can be retried.")
        if row["status"] == "uncertain" and not body.acknowledge_uncertain:
            raise HTTPException(
                409,
                "Check the recipient’s mailbox and acknowledge a possible duplicate before resending.",
            )
        db.execute(
            "UPDATE email_outbox SET status='queued',attempts=0,next_attempt_at=0,error_code=NULL WHERE id=?",
            (delivery_id,),
        )
    return {"id": delivery_id, "status": "queued"}
