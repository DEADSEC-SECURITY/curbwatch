"""Standards-based OIDC authorization code login, using Authlib/JoseRFC validation."""

import json
import secrets
import time

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oidc.core import CodeIDToken
import httpx
from httpx import AsyncClient as HttpClient
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jws import JWSRegistry
from fastapi import Request
from fastapi.responses import RedirectResponse

from . import config
from .auth import (
    router,
    FLOW_COOKIE,
    COOKIE,
    base_url,
    cookie_options,
    connect,
    digest,
    normalize_email,
    safe_url,
    sso_settings,
    sso_revision,
    start_session,
    validate_sso,
)

# No shared-secret or unsigned ID tokens: provider public keys only.
ALGORITHMS = {
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
    "PS256",
    "PS384",
    "PS512",
    "EdDSA",
}


async def load_metadata(settings):
    validate_sso(settings)
    async with HttpClient(timeout=10) as client:
        response = await client.get(settings["discovery_url"])
        response.raise_for_status()
        metadata = response.json()
    if metadata["issuer"] != settings["issuer"]:
        raise ValueError("OIDC discovery issuer differs from the configured issuer.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        safe_url(metadata[key])
    return metadata


def oauth_client(settings):
    return AsyncOAuth2Client(
        settings["client_id"],
        settings["client_secret"] or None,
        scope="openid email profile",
        redirect_uri=base_url() + "/api/auth/oidc/callback",
        token_endpoint_auth_method=settings["token_endpoint_auth_method"],
        code_challenge_method="S256",
        timeout=15,
    )


async def exchange_identity(settings, flow, code):
    metadata = await load_metadata(settings)
    async with oauth_client(settings) as client:
        token = await client.fetch_token(
            metadata["token_endpoint"], code=code, code_verifier=flow["verifier"]
        )
    async with HttpClient(timeout=10) as client:
        response = await client.get(metadata["jwks_uri"])
        response.raise_for_status()
        keys = KeySet.import_key_set(response.json())
    algorithms = list(
        ALGORITHMS.intersection(metadata.get("id_token_signing_alg_values_supported", ["RS256"]))
    )
    if not algorithms:
        raise ValueError("The provider must support an asymmetric signing algorithm.")
    decoded = jwt.decode(
        token["id_token"],
        keys,
        registry=JWSRegistry(algorithms=algorithms, strict_check_header=False),
    )
    claims = CodeIDToken(
        decoded.claims,
        decoded.header,
        {"iss": {"essential": True, "value": settings["issuer"]}},
        {
            "nonce": flow["nonce"],
            "client_id": settings["client_id"],
            "access_token": token.get("access_token"),
        },
    )
    claims.validate(leeway=30)
    # Explicit checks also cover ID token validators' optional OIDC claims.
    if (
        claims.get("iss") != settings["issuer"]
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"]
    ):
        raise ValueError("Invalid identity claims.")
    audience = claims.get("aud")
    if settings["client_id"] not in (audience if isinstance(audience, list) else [audience]):
        raise ValueError("Invalid audience.")
    if claims.get("nonce") != flow["nonce"]:
        raise ValueError("Invalid nonce.")
    return dict(claims)


def admit_identity(db, settings, claims):
    identity = db.execute(
        """SELECT u.* FROM auth_identities i JOIN users u ON u.id=i.user_id
                           WHERE i.issuer=? AND i.subject=?""",
        (settings["issuer"], claims["sub"]),
    ).fetchone()
    if identity:
        if identity["status"] != "active":
            raise ValueError("Access is disabled.")
        return identity
    if claims.get("email_verified") is not True or not isinstance(claims.get("email"), str):
        raise ValueError("A verified email is required to link the account.")
    user = db.execute(
        "SELECT * FROM users WHERE email=?", (normalize_email(claims["email"]),)
    ).fetchone()
    if not user or user["status"] == "disabled":
        raise ValueError("Administrator approval is required.")
    if db.execute(
        "SELECT 1 FROM auth_identities WHERE issuer=? AND user_id=?",
        (settings["issuer"], user["id"]),
    ).fetchone():
        raise ValueError("This email is already linked to another identity.")
    db.execute(
        "INSERT INTO auth_identities VALUES (?,?,?)",
        (settings["issuer"], claims["sub"], user["id"]),
    )
    db.execute("UPDATE users SET status='active' WHERE id=?", (user["id"],))
    db.execute("DELETE FROM auth_invites WHERE user_id=?", (user["id"],))
    return db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()


@router.get("/api/auth/oidc/start", include_in_schema=False)
async def oidc_start():
    settings, _ = sso_settings()
    if not settings["enabled"]:
        return RedirectResponse(base_url() + "/#login?error=sso_disabled", status_code=303)
    try:
        metadata = await load_metadata(settings)
        state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        async with oauth_client(settings) as client:
            url, _ = client.create_authorization_url(
                metadata["authorization_endpoint"], state=state, nonce=nonce, code_verifier=verifier
            )
        flow = {"nonce": nonce, "verifier": verifier, "revision": sso_revision(settings)}
        with connect() as db:
            db.execute("DELETE FROM auth_flows WHERE expires_at<=?", (int(time.time()),))
            db.execute(
                "INSERT INTO auth_flows VALUES (?,?,?,?)",
                (digest(state), digest(browser), json.dumps(flow), int(time.time()) + 600),
            )
        response = RedirectResponse(url, status_code=303)
        response.set_cookie(FLOW_COOKIE, browser, max_age=600, **cookie_options())
        return response
    except (ValueError, KeyError, httpx.HTTPError):
        return RedirectResponse(base_url() + "/#login?error=sso_unavailable", status_code=303)


@router.get("/api/auth/oidc/callback", include_in_schema=False)
async def oidc_callback(request: Request, state: str = "", code: str = ""):
    response = RedirectResponse(base_url() + "/#login?error=sso_failed", status_code=303)
    response.delete_cookie(FLOW_COOKIE, **cookie_options())
    settings, _ = sso_settings()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM auth_flows WHERE state_hash=?", (digest(state),)).fetchone()
        if not row or row["browser_hash"] != digest(request.cookies.get(FLOW_COOKIE, "")):
            return response
        db.execute("DELETE FROM auth_flows WHERE state_hash=?", (digest(state),))
    if row["expires_at"] <= time.time() or not code or not settings["enabled"]:
        return response
    flow = json.loads(row["data"])
    if flow["revision"] != sso_revision(settings):
        return response
    try:
        claims = await exchange_identity(settings, flow, code)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Configuration may have been disabled/changed while the token exchange was in flight.
            current, _ = sso_settings()
            if not current["enabled"] or sso_revision(current) != flow["revision"]:
                return response
            user = admit_identity(db, settings, claims)
            response = RedirectResponse(base_url() + "/#map", status_code=303)
            response.delete_cookie(FLOW_COOKIE, **cookie_options())
            start_session(
                db,
                user,
                response,
                request.cookies.get(COOKIE, ""),
                session_hours=config.AUTH_SSO_SESSION_HOURS,
            )
        return response
    except Exception:
        # Tokens, authorization codes, claims and provider errors must never be echoed or logged.
        return response
