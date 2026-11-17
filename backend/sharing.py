"""Revocable map capabilities. Owner management is never mounted in the viewer."""

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from . import config
from .db import connect, now

owner_router = APIRouter(prefix="/api/shares", tags=["Map sharing"])
PUBLIC_FIELDS = ("id", "name", "created_at", "expires_at", "revoked_at")
INVALID_LINK = "This map link is unavailable. It may have expired or been revoked."
share_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="MapLink",
    description="The secret from a valid, unexpired, unrevoked map link.",
)


class ShareCreate(BaseModel):
    name: str = Field(default="Map link", max_length=80)
    expires_in_days: Literal[7, 30] | None = 30

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        return value.strip() or "Map link"


def share_metadata(row):
    data = {field: row[field] for field in PUBLIC_FIELDS}
    data["status"] = (
        "revoked"
        if row["revoked_at"]
        else "expired"
        if row["expires_at"]
        and datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc)
        else "active"
    )
    return data


@owner_router.get("")
def list_shares():
    with connect() as db:
        links = [
            share_metadata(row)
            for row in db.execute("SELECT * FROM map_shares ORDER BY created_at DESC")
        ]
    return {
        "links": links,
        "base_url": config.SHARE_BASE_URL,
        "local_only": urlsplit(config.SHARE_BASE_URL).hostname in {"127.0.0.1", "localhost", "::1"},
    }


@owner_router.post("", status_code=201)
def create_share(body: ShareCreate):
    token = secrets.token_urlsafe(32)
    created = datetime.now(timezone.utc)
    expires = (
        (created + timedelta(days=body.expires_in_days)).isoformat()
        if body.expires_in_days
        else None
    )
    with connect() as db:
        row = db.execute(
            """INSERT INTO map_shares(id,name,token_hash,created_at,expires_at)
                            VALUES (?,?,?,?,?) RETURNING *""",
            (
                uuid4().hex,
                body.name,
                hashlib.sha256(token.encode()).hexdigest(),
                created.isoformat(),
                expires,
            ),
        ).fetchone()
        return {**share_metadata(row), "url": f"{config.SHARE_BASE_URL}/share/#{token}"}


@owner_router.post("/{share_id}/revoke")
def revoke_share(share_id: str):
    with connect() as db:
        row = db.execute(
            "UPDATE map_shares SET revoked_at=COALESCE(revoked_at,?) WHERE id=? RETURNING *",
            (now(), share_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Map link not found")
        return share_metadata(row)


def require_share(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(share_bearer)],
):
    if not credentials or not re.fullmatch(r"[A-Za-z0-9_-]{43}", credentials.credentials):
        raise HTTPException(404, INVALID_LINK)
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with connect() as db:
        row = db.execute("SELECT * FROM map_shares WHERE token_hash=?", (digest,)).fetchone()
    if not row or share_metadata(row)["status"] != "active":
        raise HTTPException(404, INVALID_LINK)
