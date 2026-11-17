"""SMTP policy is readable without decrypting credentials; delivery secrets stay private."""

import ipaddress
import json
import os
import re
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator, model_validator

from . import config
from .auth import encryption
from .db import connect

DEFAULTS = dict(
    enabled=False,
    host="",
    port=587,
    security="starttls",
    username="",
    from_email="",
    from_name="Curbwatch",
    reply_to=None,
    ticket_alerts=True,
    monthly_reports=True,
    report_day=1,
    report_hour=9,
    report_minute=15,
)
EMAIL = TypeAdapter(EmailStr)


def recipient_email(value):
    try:
        return str(EMAIL.validate_python(value.strip())).lower() if value else None
    except ValueError:
        return None


def loopback_host(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class MailSettings(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: str = Field(default="starttls", pattern="^(starttls|tls|none)$")
    username: str = Field(default="", max_length=300)
    password: str | None = Field(
        default=None, max_length=4000, repr=False, json_schema_extra={"writeOnly": True}
    )
    from_email: EmailStr | None = None
    from_name: str = Field(default="Curbwatch", min_length=1, max_length=80)
    reply_to: EmailStr | None = None
    ticket_alerts: bool = True
    monthly_reports: bool = True
    report_day: int = Field(default=1, ge=1, le=28)
    report_hour: int = Field(default=9, ge=0, le=23)
    report_minute: int = Field(default=15, ge=0, le=59)

    @field_validator("from_email", "reply_to", mode="before")
    @classmethod
    def optional_email(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("host", "username", "from_name")
    @classmethod
    def header_safe(cls, value):
        if any(char in value for char in "\r\n\0"):
            raise ValueError("Use a single line without control characters.")
        return value.strip()

    @field_validator("host")
    @classmethod
    def hostname_only(cls, value):
        if value and (
            any(c.isspace() for c in value) or "/" in value or "@" in value or "://" in value
        ):
            raise ValueError("Enter a server hostname or IP address, without a URL or port.")
        if value:
            try:
                ipaddress.ip_address(value)
            except ValueError:
                value = value.encode("idna").decode()
                if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?", value):
                    raise ValueError("Enter a hostname without a URL or port.")
        return value

    @model_validator(mode="after")
    def transport(self):
        if self.enabled and (not self.host or not self.from_email):
            raise ValueError("Set the SMTP server and sender email before enabling delivery.")
        if self.security == "none" and self.host and not loopback_host(self.host):
            raise ValueError(
                "Unencrypted SMTP is only available for loopback test servers. Use STARTTLS or TLS."
            )
        return self


def mail_settings(*, secret=False, db=None):
    managed = any(
        name in os.environ
        for name in (
            "PARKING_SMTP_HOST",
            "PARKING_SMTP_PORT",
            "PARKING_SMTP_SECURITY",
            "PARKING_SMTP_USERNAME",
            "PARKING_SMTP_PASSWORD",
            "PARKING_SMTP_PASSWORD_FILE",
            "PARKING_SMTP_FROM_EMAIL",
            "PARKING_SMTP_FROM_NAME",
            "PARKING_SMTP_REPLY_TO",
            "PARKING_EMAIL_ENABLED",
            "PARKING_EMAIL_TICKET_ALERTS",
            "PARKING_EMAIL_MONTHLY_REPORTS",
            "PARKING_EMAIL_REPORT_DAY",
            "PARKING_EMAIL_REPORT_HOUR",
            "PARKING_EMAIL_REPORT_MINUTE",
        )
    )
    encrypted = None
    if managed:
        settings = {
            **DEFAULTS,
            "host": os.environ.get("PARKING_SMTP_HOST", ""),
            "port": int(os.environ.get("PARKING_SMTP_PORT", "587")),
            "security": os.environ.get("PARKING_SMTP_SECURITY", "starttls"),
            "username": os.environ.get("PARKING_SMTP_USERNAME", ""),
            "from_email": os.environ.get("PARKING_SMTP_FROM_EMAIL", ""),
            "from_name": os.environ.get("PARKING_SMTP_FROM_NAME", "Curbwatch"),
            "reply_to": os.environ.get("PARKING_SMTP_REPLY_TO") or None,
            "report_day": int(os.environ.get("PARKING_EMAIL_REPORT_DAY", "1")),
            "report_hour": int(os.environ.get("PARKING_EMAIL_REPORT_HOUR", "9")),
            "report_minute": int(os.environ.get("PARKING_EMAIL_REPORT_MINUTE", "15")),
        }
        for key, env, default in (
            ("enabled", "PARKING_EMAIL_ENABLED", "false"),
            ("ticket_alerts", "PARKING_EMAIL_TICKET_ALERTS", "true"),
            ("monthly_reports", "PARKING_EMAIL_MONTHLY_REPORTS", "true"),
        ):
            settings[key] = config.flag(env, default == "true")
        password_file = os.environ.get("PARKING_SMTP_PASSWORD_FILE")
        has_password = bool(password_file or os.environ.get("PARKING_SMTP_PASSWORD"))
        if secret:
            settings["password"] = (
                Path(password_file).read_text().rstrip("\r\n")
                if password_file
                else os.environ.get("PARKING_SMTP_PASSWORD", "")
            )
    else:
        if db is None:
            with connect() as connection:
                row = connection.execute(
                    "SELECT value FROM app_meta WHERE key='mail_settings'"
                ).fetchone()
        else:
            row = db.execute("SELECT value FROM app_meta WHERE key='mail_settings'").fetchone()
        saved = json.loads(row["value"]) if row else {}
        encrypted = saved.pop("password_encrypted", None)
        settings = {**DEFAULTS, **saved}
        has_password = bool(encrypted)
        if secret:
            settings["password"] = (
                encryption().decrypt(encrypted.encode()).decode() if encrypted else ""
            )
    return settings, managed, has_password


def validate_delivery_settings(settings, has_password):
    MailSettings.model_validate(settings)
    if settings["enabled"] and bool(settings["username"]) != has_password:
        raise ValueError(
            "Provide both SMTP username and password, or leave both empty for a trusted relay."
        )


def save_mail_settings(body):
    _, managed, has_password = mail_settings()
    if managed:
        raise ValueError("SMTP is managed by deployment configuration.")
    data = body.model_dump(exclude={"password"})
    data["from_email"] = str(body.from_email or "")
    data["reply_to"] = str(body.reply_to) if body.reply_to else None
    with connect() as db:
        row = db.execute("SELECT value FROM app_meta WHERE key='mail_settings'").fetchone()
        previous = json.loads(row["value"]) if row else {}
        encrypted = previous.get("password_encrypted")
        if body.password is not None:
            encrypted = (
                encryption().encrypt(body.password.encode()).decode() if body.password else None
            )
        validate_delivery_settings(data, bool(encrypted))
        data["password_encrypted"] = encrypted
        db.execute(
            "INSERT OR REPLACE INTO app_meta VALUES ('mail_settings',?)", (json.dumps(data),)
        )


def public_mail_settings():
    settings, managed, has_password = mail_settings()
    return {
        **settings,
        "has_password": has_password,
        "managed_by_environment": managed,
        "timezone": config.TIMEZONE,
    }
