"""Local accounts, opaque server sessions, invitations and admin-only settings."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, EmailStr, Field, field_validator
from pwdlib import PasswordHash

from . import config
from .db import connect, now

COOKIE = "curbwatch_session"
FLOW_COOKIE = "curbwatch_oidc"
passwords = PasswordHash.recommended()
DUMMY_PASSWORD = passwords.hash(secrets.token_urlsafe(32))
router = APIRouter()
session_cookie = APIKeyCookie(name=COOKIE, auto_error=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def init_auth(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL CHECK(role IN ('admin','member')),
        status TEXT NOT NULL CHECK(status IN ('invited','active','disabled')),
        password_hash TEXT, created_at TEXT NOT NULL, last_login_at TEXT
      );
      CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        csrf TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auth_invites (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        expires_at INTEGER NOT NULL, created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auth_identities (
        issuer TEXT NOT NULL, subject TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
        PRIMARY KEY(issuer,subject), UNIQUE(issuer,user_id)
      );
      CREATE TABLE IF NOT EXISTS auth_flows (
        state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, data TEXT NOT NULL,
        expires_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auth_attempts (
        key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL
      );
    """)


def public_user(row):
    return {
        key: row[key]
        for key in ("id", "email", "name", "role", "status", "created_at", "last_login_at")
    }


def get_session(request):
    token = request.cookies.get(COOKIE, "")
    if len(token) != 43:
        return None
    with connect() as db:
        return db.execute(
            """SELECT u.*,s.csrf,s.token_hash FROM auth_sessions s JOIN users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>? AND u.status='active' """,
            (digest(token), int(time.time())),
        ).fetchone()


def require_user(request: Request, cookie=Depends(session_cookie)):
    user = getattr(request.state, "user", None) or get_session(request)
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def require_admin(user=Depends(require_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access is required.")
    return user


def cookie_options():
    return dict(httponly=True, secure=config.AUTH_COOKIE_SECURE, samesite="lax", path="/")


def start_session(db, user, response, old_token="", *, session_hours=None):
    lifetime = (config.AUTH_SESSION_HOURS if session_hours is None else session_hours) * 3600
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute(
        "DELETE FROM auth_sessions WHERE expires_at<=? OR token_hash=?",
        (int(time.time()), digest(old_token)),
    )
    db.execute(
        "INSERT INTO auth_sessions VALUES (?,?,?,?,?)",
        (
            digest(token),
            user["id"],
            csrf,
            int(time.time()) + lifetime,
            now(),
        ),
    )
    db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), user["id"]))
    response.set_cookie(COOKIE, token, max_age=lifetime, **cookie_options())
    return {"user": public_user(user), "csrf_token": csrf}


def base_url():
    return safe_url(config.AUTH_BASE_URL, origin_only=True)


def safe_url(value, origin_only=False):
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or (parts.scheme != "https" and parts.hostname not in ("127.0.0.1", "localhost", "::1"))
        or (origin_only and parts.path not in ("", "/"))
    ):
        raise ValueError(
            "Use HTTPS URLs, or loopback HTTP for local testing. App URL must be an origin."
        )
    return value.rstrip("/") if origin_only else value


def encryption():
    key = os.environ.get("PARKING_AUTH_KEY")
    if not key:
        path = Path(os.environ.get("PARKING_AUTH_KEY_FILE", config.DATA_DIR / "auth.key"))
        import fcntl

        try:
            key = path.read_bytes().strip()
        except FileNotFoundError:
            key = None
        if not key:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, "r+b") as target:
                fcntl.flock(target, fcntl.LOCK_EX)
                key = target.read().strip()
                if not key:
                    key = Fernet.generate_key()
                    target.write(key)
                    target.flush()

    return Fernet(key)


SSO_DEFAULT = dict(
    enabled=False,
    name="Single sign-on",
    issuer="",
    discovery_url="",
    client_id="",
    client_secret="",
    token_endpoint_auth_method="client_secret_basic",
)


def sso_settings():
    managed = any(name.startswith("PARKING_OIDC_") for name in os.environ)
    if managed:
        # Deployment config is independent of a saved provider/key, including recovery.
        settings = {
            **SSO_DEFAULT,
            "enabled": config.flag(
                "PARKING_OIDC_ENABLED", bool(os.environ.get("PARKING_OIDC_ISSUER"))
            ),
            "name": os.environ.get("PARKING_OIDC_NAME", "Single sign-on"),
            "issuer": os.environ.get("PARKING_OIDC_ISSUER", ""),
            "discovery_url": os.environ.get("PARKING_OIDC_DISCOVERY_URL", ""),
            "client_id": os.environ.get("PARKING_OIDC_CLIENT_ID", ""),
            "client_secret": os.environ.get("PARKING_OIDC_CLIENT_SECRET", ""),
            "token_endpoint_auth_method": os.environ.get(
                "PARKING_OIDC_AUTH_METHOD", "client_secret_basic"
            ),
        }
        secret_file = os.environ.get("PARKING_OIDC_CLIENT_SECRET_FILE")
        if secret_file:
            settings["client_secret"] = Path(secret_file).read_text().strip()
    else:
        with connect() as db:
            row = db.execute("SELECT value FROM app_meta WHERE key='sso_settings'").fetchone()
        settings = {
            **SSO_DEFAULT,
            **(json.loads(encryption().decrypt(row["value"].encode())) if row else {}),
        }
    if not settings["discovery_url"] and settings["issuer"]:
        settings["discovery_url"] = (
            settings["issuer"].rstrip("/") + "/.well-known/openid-configuration"
        )
    return settings, managed


def sso_revision(settings):
    return digest(json.dumps(settings, sort_keys=True))


def validate_sso(settings):
    if settings["enabled"]:
        safe_url(settings["issuer"])
        safe_url(settings["discovery_url"])
        base_url()
        if not settings["client_id"] or (
            settings["token_endpoint_auth_method"] != "none" and not settings["client_secret"]
        ):
            raise ValueError(
                "Set the issuer, discovery URL, client ID and client secret before enabling SSO."
            )
    return settings


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class Password(BaseModel):
    current_password: str = Field(default="", max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class AcceptInvite(BaseModel):
    token: str = Field(min_length=43, max_length=43)
    name: str = Field(default="", max_length=80)
    password: str = Field(min_length=12, max_length=1024)


class AddUser(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=80)
    role: str = Field(default="member", pattern="^(admin|member)$")


class UpdateUser(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|member)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class SSOSettings(BaseModel):
    enabled: bool = False
    name: str = Field(default="Single sign-on", min_length=1, max_length=80)
    issuer: str = Field(default="", max_length=1000)
    discovery_url: str = Field(default="", max_length=1000)
    client_id: str = Field(default="", max_length=300)
    client_secret: str | None = Field(default=None, max_length=4000)
    token_endpoint_auth_method: str = Field(
        default="client_secret_basic", pattern="^(client_secret_basic|client_secret_post|none)$"
    )

    @field_validator("issuer", "discovery_url", "client_id", "name")
    @classmethod
    def trim(cls, value):
        return value.strip()


def normalize_email(value):
    return str(value).strip().lower()


def check_rate(db, request, email):
    timestamp = int(time.time())
    db.execute("DELETE FROM auth_attempts WHERE expires_at<=?", (timestamp,))
    keys = [
        (digest("email:" + email), 10),
        (digest("ip:" + (request.client.host if request.client else "unknown")), 40),
    ]
    for key, limit in keys:
        row = db.execute("SELECT count FROM auth_attempts WHERE key=?", (key,)).fetchone()
        if row and row["count"] >= limit:
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
    for key, _ in keys:
        db.execute(
            """INSERT INTO auth_attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1""",
            (key, timestamp + 900),
        )


@router.get("/api/auth/config")
def auth_config():
    settings, _ = sso_settings()
    with connect() as db:
        setup = not db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    return {
        "setup_required": setup,
        "sso_enabled": settings["enabled"],
        "sso_name": settings["name"],
    }


@router.get("/api/auth/session")
def session(user=Depends(require_user)):
    return {"user": public_user(user), "csrf_token": user["csrf"]}


@router.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    email = normalize_email(body.email)
    # Commit rate counters even when credential validation fails.
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        check_rate(db, request, email)
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        valid = passwords.verify(
            body.password,
            user["password_hash"] if user and user["password_hash"] else DUMMY_PASSWORD,
        )
        if not valid or not user or user["status"] != "active":
            raise HTTPException(401, "Email or password is incorrect, or access is unavailable.")
        db.execute("DELETE FROM auth_attempts WHERE key=?", (digest("email:" + email),))
        return start_session(db, user, response, request.cookies.get(COOKIE, ""))


@router.post("/api/auth/logout")
def logout(response: Response, user=Depends(require_user)):
    with connect() as db:
        db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (user["token_hash"],))
    response.delete_cookie(COOKIE, **cookie_options())
    return {"ok": True}


@router.post("/api/auth/password")
def change_password(body: Password, response: Response, user=Depends(require_user)):
    # SSO-only accounts must use an admin invitation to add local credentials.
    if not user["password_hash"] or not passwords.verify(
        body.current_password, user["password_hash"]
    ):
        raise HTTPException(
            403,
            "Your current password is required. For SSO-only accounts, ask an admin for an invitation.",
        )
    with connect() as db:
        db.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (passwords.hash(body.new_password), user["id"]),
        )
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user["id"],))
        db.execute("DELETE FROM auth_invites WHERE user_id=?", (user["id"],))
        return start_session(db, user, response)


def invitation(db, user_id):
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + config.INVITE_TTL_HOURS * 3600
    db.execute("DELETE FROM auth_invites WHERE user_id=?", (user_id,))
    db.execute(
        "INSERT INTO auth_invites VALUES (?,?,?,?)", (digest(token), user_id, expires, now())
    )
    return {"url": base_url() + "/#invite/" + token, "expires_at": expires}


@router.post("/api/auth/invitations/accept")
def accept_invite(body: AcceptInvite, request: Request, response: Response):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        invite = db.execute(
            """SELECT u.*,i.expires_at FROM auth_invites i JOIN users u ON i.user_id=u.id
                             WHERE i.token_hash=?""",
            (digest(body.token),),
        ).fetchone()
        if not invite or invite["expires_at"] <= time.time() or invite["status"] == "disabled":
            raise HTTPException(
                400,
                "This invitation has expired or is unavailable. Ask an administrator for a new link.",
            )
        db.execute(
            "UPDATE users SET name=?,password_hash=?,status='active' WHERE id=?",
            (body.name.strip() or invite["name"], passwords.hash(body.password), invite["id"]),
        )
        db.execute("DELETE FROM auth_invites WHERE user_id=?", (invite["id"],))
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (invite["id"],))
        user = db.execute("SELECT * FROM users WHERE id=?", (invite["id"],)).fetchone()
        return start_session(db, user, response, request.cookies.get(COOKIE, ""))


@router.get("/api/admin/users")
def list_users(user=Depends(require_admin)):
    with connect() as db:
        return [public_user(row) for row in db.execute("SELECT * FROM users ORDER BY id")]


@router.post("/api/admin/users", status_code=201)
def add_user(body: AddUser, user=Depends(require_admin)):
    try:
        with connect() as db:
            added = db.execute(
                "INSERT INTO users(email,name,role,status,created_at) VALUES (?,?,?,'invited',?) RETURNING *",
                (normalize_email(body.email), body.name.strip(), body.role, now()),
            ).fetchone()
            return {"user": public_user(added), "invitation": invitation(db, added["id"])}
    except sqlite3.IntegrityError:
        raise HTTPException(
            409, "This email already has an account. You can create a new invitation for it."
        )


@router.patch("/api/admin/users/{user_id}")
def update_user(user_id: int, body: UpdateUser, admin=Depends(require_admin)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "Account not found.")
        role, status = body.role or user["role"], body.status or user["status"]
        if (
            user["role"] == "admin"
            and user["status"] == "active"
            and (role != "admin" or status != "active")
        ):
            count = db.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND status='active'"
            ).fetchone()[0]
            if count <= 1:
                raise HTTPException(409, "Keep at least one active administrator.")
        if status == "active" and user["status"] == "invited":
            raise HTTPException(
                409,
                "This person must accept an invitation or sign in with their verified SSO email first.",
            )
        db.execute("UPDATE users SET role=?,status=? WHERE id=?", (role, status, user_id))
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
        if status == "disabled":
            db.execute("DELETE FROM auth_invites WHERE user_id=?", (user_id,))
        return public_user(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


@router.post("/api/admin/users/{user_id}/invite", status_code=201)
def invite_user(user_id: int, admin=Depends(require_admin)):
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or user["status"] == "disabled":
            raise HTTPException(409, "Enable this account before creating an invitation.")
        return invitation(db, user_id)


def public_sso():
    settings, managed = sso_settings()
    return {
        **{key: value for key, value in settings.items() if key != "client_secret"},
        "has_client_secret": bool(settings["client_secret"]),
        "managed_by_environment": managed,
        "callback_url": base_url() + "/api/auth/oidc/callback",
    }


@router.get("/api/admin/sso")
def get_sso(user=Depends(require_admin)):
    return public_sso()


@router.put("/api/admin/sso")
def put_sso(body: SSOSettings, user=Depends(require_admin)):
    current, managed = sso_settings()
    if managed:
        raise HTTPException(409, "SSO is managed by deployment configuration.")
    settings = body.model_dump()
    settings["client_secret"] = (
        current["client_secret"] if body.client_secret is None else body.client_secret
    )
    if settings["issuer"] and not settings["discovery_url"]:
        settings["discovery_url"] = (
            settings["issuer"].rstrip("/") + "/.well-known/openid-configuration"
        )
    try:
        validate_sso(settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO app_meta VALUES ('sso_settings',?)",
            (encryption().encrypt(json.dumps(settings).encode()).decode(),),
        )
        db.execute("DELETE FROM auth_flows")
    return public_sso()


def create_admin(email, password, name="Administrator", reset=False, only_if_empty=False):
    from pydantic import TypeAdapter

    email = normalize_email(TypeAdapter(EmailStr).validate_python(email))
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Use a password of 12–1024 characters.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if only_if_empty and db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            if not reset:
                raise ValueError("That account already exists. Use reset-admin to recover access.")
            user_id = existing["id"]
            db.execute(
                "UPDATE users SET role='admin',status='active',password_hash=? WHERE id=?",
                (passwords.hash(password), user_id),
            )
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM auth_invites WHERE user_id=?", (user_id,))
        else:
            db.execute(
                "INSERT INTO users(email,name,role,status,password_hash,created_at) VALUES (?,?,'admin','active',?,?)",
                (email, name, passwords.hash(password), now()),
            )


def bootstrap_admin():
    with connect() as db:
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
    email = os.environ.get("PARKING_BOOTSTRAP_ADMIN_EMAIL")
    password_file = os.environ.get("PARKING_BOOTSTRAP_ADMIN_PASSWORD_FILE")
    password = (
        Path(password_file).read_text().rstrip("\r\n")
        if password_file
        else os.environ.get("PARKING_BOOTSTRAP_ADMIN_PASSWORD")
    )
    if email and password:
        create_admin(email, password, only_if_empty=True)
