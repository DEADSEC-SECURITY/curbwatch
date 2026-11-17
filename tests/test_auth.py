import hashlib
import json
import time
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
import httpx
import pytest

from backend import auth, config, oidc
from backend.auth import create_admin, digest
from backend.db import connect, init_db
from backend.main import app


@pytest.fixture
def anonymous(database, monkeypatch):
    import backend.main

    monkeypatch.setattr(backend.main, "init_db", lambda: init_db(seed=False))
    with TestClient(app) as test:
        yield test


def token_from_invite(response):
    return urlsplit(response.json()["invitation"]["url"]).fragment.removeprefix("invite/")


def test_empty_install_is_closed_and_bootstrap_is_not_public(anonymous):
    assert anonymous.get("/api/auth/config").json()["setup_required"] is True
    for path in (
        "/api/cars",
        "/api/tickets",
        "/api/overview",
        "/api/checks",
        "/api/activity",
        "/api/streets",
        "/api/shares",
        "/api/admin/users",
        "/docs",
        "/openapi.json",
    ):
        response = anonymous.get(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    assert anonymous.post("/api/auth/signup", json={}).status_code != 200
    assert anonymous.get("/api/health").status_code == 200
    assert anonymous.get("/").status_code == 200
    assert "password_hash" not in anonymous.get("/api/auth/config").text


def test_bootstrap_is_one_time_and_preserves_data(database, monkeypatch):
    with connect() as db:
        db.execute("INSERT INTO cars(name,plate,created_at) VALUES ('Keep me','KEEP123','now')")
    monkeypatch.setenv("PARKING_BOOTSTRAP_ADMIN_EMAIL", "first@example.com")
    monkeypatch.setenv("PARKING_BOOTSTRAP_ADMIN_PASSWORD", "Initial-password-123")
    auth.bootstrap_admin()
    monkeypatch.setenv("PARKING_BOOTSTRAP_ADMIN_EMAIL", "second@example.com")
    auth.bootstrap_admin()
    with connect() as db:
        assert db.execute("SELECT email FROM users").fetchall()[0][0] == "first@example.com"
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        row = db.execute("SELECT password_hash FROM users").fetchone()[0]
        assert row.startswith("$argon2id$") and "Initial-password" not in row
        assert db.execute("SELECT plate FROM cars").fetchone()[0] == "KEEP123"


def test_session_csrf_expiry_logout_and_cross_origin(client):
    response = client.get("/api/auth/session")
    assert response.json()["user"]["role"] == "admin"
    assert "password_hash" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/checks", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert (
        client.post("/api/checks", json={}, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/login", content="email=anything", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": "bad"}
        ).status_code
        == 401
    )
    with connect() as db:
        row = db.execute("SELECT * FROM auth_sessions").fetchone()
        assert client.cookies.get(auth.COOKIE) not in json.dumps(dict(row))
        db.execute("UPDATE auth_sessions SET expires_at=0")
    assert client.get("/api/cars").status_code == 401
    session = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "Testing-password-123!"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf_token"]
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.get("/api/cars").status_code == 401


def test_invites_are_required_single_use_hashed_expiring_and_reissuable(client):
    response = client.post(
        "/api/admin/users", json={"email": "New@Example.com", "name": "New person"}
    )
    assert response.status_code == 201
    token = token_from_invite(response)
    user_id = response.json()["user"]["id"]
    with connect() as db:
        row = db.execute("SELECT * FROM auth_invites").fetchone()
        assert row["token_hash"] == digest(token) and token not in json.dumps(dict(row))
    assert token not in client.get("/api/admin/users").text
    response2 = client.post(f"/api/admin/users/{user_id}/invite", json={})
    new_token = urlsplit(response2.json()["url"]).fragment.removeprefix("invite/")
    body = {"token": token, "name": "New person", "password": "Member-password-123"}
    with TestClient(app) as member:
        assert member.post("/api/auth/invitations/accept", json=body).status_code == 400
        body["token"] = new_token
        assert member.post("/api/auth/invitations/accept", json=body).status_code == 200
        assert member.post("/api/auth/invitations/accept", json=body).status_code == 400
        assert member.get("/api/cars").status_code == 200
        assert member.get("/api/admin/users").status_code == 403
        assert member.get("/api/admin/sso").status_code == 403
        assert member.get("/api/shares").status_code == 403
        session = member.get("/api/auth/session").json()
        member.headers["X-CSRF-Token"] = session["csrf_token"]
        assert member.post("/api/admin/users", json={"email": "bad@example.com"}).status_code == 403
        client.patch(f"/api/admin/users/{user_id}", json={"status": "disabled"}).raise_for_status()
        assert member.get("/api/cars").status_code == 401
        assert (
            member.post(
                "/api/auth/login",
                json={"email": "new@example.com", "password": "Member-password-123"},
            ).status_code
            == 401
        )
    # Disabled account cannot receive invitations.
    assert client.post(f"/api/admin/users/{user_id}/invite", json={}).status_code == 409
    client.patch(f"/api/admin/users/{user_id}", json={"status": "active"}).raise_for_status()
    invite = client.post(f"/api/admin/users/{user_id}/invite", json={}).json()
    with connect() as db:
        db.execute("UPDATE auth_invites SET expires_at=0")
    with TestClient(app) as member:
        assert (
            member.post(
                "/api/auth/invitations/accept",
                json={
                    "token": urlsplit(invite["url"]).fragment[7:],
                    "password": "Another-password-123",
                },
            ).status_code
            == 400
        )


def test_last_admin_password_rotation_and_recovery(client):
    me = client.get("/api/auth/session").json()["user"]["id"]
    for changes in ({"role": "member"}, {"status": "disabled"}):
        assert client.patch(f"/api/admin/users/{me}", json=changes).status_code == 409
    original = client.cookies.get(auth.COOKIE)
    response = client.post(
        "/api/auth/password",
        json={"current_password": "Testing-password-123!", "new_password": "Changed-password-123"},
    )
    assert response.status_code == 200 and original != client.cookies.get(auth.COOKIE)
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    with TestClient(app) as stale:
        stale.cookies.set(auth.COOKIE, original)
        assert stale.get("/api/cars").status_code == 401
    create_admin("admin@example.com", "Recovered-password-123", reset=True)
    assert client.get("/api/cars").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Recovered-password-123"},
        ).status_code
        == 200
    )


def test_login_rate_limit(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"email": "unknown@example.com", "password": "bad"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "unknown@example.com", "password": "bad"}
        ).status_code
        == 429
    )


def configure_sso(client):
    body = dict(
        enabled=True,
        name="Authentik",
        issuer="https://id.example/application/o/curbwatch/",
        client_id="curbwatch",
        client_secret="SSO-super-secret",
    )
    response = client.put("/api/admin/sso", json=body)
    assert response.status_code == 200, response.text
    return auth.sso_settings()[0]


def test_sso_secrets_encrypted_redacted_and_environment_managed(client, monkeypatch):
    settings = configure_sso(client)
    assert "SSO-super-secret" not in client.get("/api/admin/sso").text
    assert client.get("/api/admin/sso").json()["has_client_secret"] is True
    with connect() as db:
        assert (
            "SSO-super-secret"
            not in db.execute("SELECT value FROM app_meta WHERE key='sso_settings'").fetchone()[0]
        )
    response = client.put(
        "/api/admin/sso", json={**settings, "name": "New label", "client_secret": None}
    )
    assert response.status_code == 200
    assert auth.sso_settings()[0]["client_secret"] == "SSO-super-secret"
    assert (config.DATA_DIR / "auth.key").stat().st_mode & 0o777 == 0o600
    assert (
        client.put(
            "/api/admin/sso", json={**settings, "issuer": "http://remote.example/"}
        ).status_code
        == 422
    )
    monkeypatch.setenv("PARKING_OIDC_ISSUER", "https://env.example/")
    monkeypatch.setenv("PARKING_OIDC_CLIENT_ID", "env-client")
    monkeypatch.setenv("PARKING_OIDC_CLIENT_SECRET", "env-secret")
    assert client.get("/api/admin/sso").json()["managed_by_environment"] is True
    assert client.put("/api/admin/sso", json=settings).status_code == 409


@pytest.fixture
def oidc_provider(client, monkeypatch):
    settings = configure_sso(client)
    key = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
    captured = []
    issuer = settings["issuer"]
    claims = dict(
        iss=issuer,
        sub="idp-admin-1",
        aud="curbwatch",
        exp=int(time.time()) + 300,
        iat=int(time.time()),
        email="admin@example.com",
        email_verified=True,
    )

    def handler(request):
        if ".well-known/" in request.url.path:
            return httpx.Response(
                200,
                json=dict(
                    issuer=issuer,
                    authorization_endpoint="https://id.example/authorize",
                    token_endpoint="https://id.example/token",
                    jwks_uri="https://id.example/jwks",
                    id_token_signing_alg_values_supported=["RS256"],
                ),
            )
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [key.as_dict(private=False)]})
        if request.url.path == "/token":
            captured.append(parse_qs(request.content.decode()))
            return httpx.Response(
                200,
                json={
                    "access_token": "access",
                    "token_type": "Bearer",
                    "id_token": jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, key),
                },
            )
        return httpx.Response(404)

    real_httpx = httpx.AsyncClient
    real_oauth = oidc.AsyncOAuth2Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(oidc, "HttpClient", lambda **kw: real_httpx(transport=transport, **kw))
    monkeypatch.setattr(
        oidc, "AsyncOAuth2Client", lambda *a, **kw: real_oauth(*a, transport=transport, **kw)
    )
    return settings, claims, captured


def begin_flow(browser, claims):
    response = browser.get("/api/auth/oidc/start", follow_redirects=False)
    assert response.status_code == 303
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"] and params["scope"] == [
        "openid email profile"
    ]
    claims["nonce"] = params["nonce"][0]
    return params


def finish_flow(browser, params):
    return browser.get(
        "/api/auth/oidc/callback",
        params={"state": params["state"][0], "code": "one-use-code"},
        follow_redirects=False,
    )


def issued_session_cookie(response):
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return cookies[auth.COOKIE]


def test_password_login_uses_its_own_configured_lifetime(client, monkeypatch):
    timestamp = 1_900_000_000
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=lambda: timestamp))
    monkeypatch.setattr(config, "AUTH_SESSION_HOURS", 12)
    monkeypatch.setattr(config, "AUTH_SSO_SESSION_HOURS", 720)
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "Testing-password-123!"},
    )
    assert response.status_code == 200
    cookie = issued_session_cookie(response)
    assert int(cookie["max-age"]) == 12 * 3600
    with connect() as db:
        session = db.execute(
            "SELECT expires_at FROM auth_sessions WHERE token_hash=?", (digest(cookie.value),)
        ).fetchone()
        assert session["expires_at"] == timestamp + 12 * 3600


@pytest.mark.parametrize("hours", [720, 1080])
def test_sso_cookie_and_server_session_use_extended_absolute_lifetime(
    client, oidc_provider, monkeypatch, hours
):
    _, claims, _ = oidc_provider
    timestamp = 1_900_000_000
    # Advance only the app's session clock, leaving ID-token validation on real time.
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=lambda: timestamp))
    monkeypatch.setattr(config, "AUTH_SESSION_HOURS", 8)
    monkeypatch.setattr(config, "AUTH_SSO_SESSION_HOURS", hours)
    with TestClient(app) as browser:
        response = finish_flow(browser, begin_flow(browser, claims))
        assert response.headers["location"].endswith("#map")
        cookie = issued_session_cookie(response)
        assert int(cookie["max-age"]) == hours * 3600
        assert cookie["httponly"] and cookie["samesite"].lower() == "lax"
        expected_expiry = timestamp + hours * 3600
        with connect() as db:
            assert (
                db.execute(
                    "SELECT expires_at FROM auth_sessions WHERE token_hash=?",
                    (digest(cookie.value),),
                ).fetchone()["expires_at"]
                == expected_expiry
            )
        timestamp += 9 * 3600
        assert browser.get("/api/auth/session").status_code == 200
        timestamp = expected_expiry - 1
        response = browser.get("/api/auth/session")
        assert response.status_code == 200 and "set-cookie" not in response.headers
        with connect() as db:
            assert (
                db.execute(
                    "SELECT expires_at FROM auth_sessions WHERE token_hash=?",
                    (digest(cookie.value),),
                ).fetchone()["expires_at"]
                == expected_expiry
            )
        timestamp = expected_expiry
        assert browser.get("/api/auth/session").status_code == 401
        assert browser.get("/api/cars").status_code == 401


@pytest.mark.parametrize("revocation", ["logout", "password_reset"])
def test_long_sso_sessions_can_be_revoked_immediately(client, oidc_provider, revocation):
    _, claims, _ = oidc_provider
    with TestClient(app) as browser:
        response = finish_flow(browser, begin_flow(browser, claims))
        token = issued_session_cookie(response).value
        session = browser.get("/api/auth/session").json()
        if revocation == "logout":
            browser.headers["X-CSRF-Token"] = session["csrf_token"]
            assert browser.post("/api/auth/logout", json={}).status_code == 200
        else:
            create_admin("admin@example.com", "Replacement-password-123", reset=True)
        with connect() as db:
            assert (
                db.execute(
                    "SELECT 1 FROM auth_sessions WHERE token_hash=?", (digest(token),)
                ).fetchone()
                is None
            )
        browser.cookies.set(auth.COOKIE, token)
        assert browser.get("/api/auth/session").status_code == 401


def test_oidc_full_round_trip_and_browser_bound_single_use_state(client, oidc_provider):
    settings, claims, captured = oidc_provider
    with TestClient(app) as browser, TestClient(app) as attacker:
        params = begin_flow(browser, claims)
        assert finish_flow(attacker, params).headers["location"].endswith("sso_failed")
        response = finish_flow(browser, params)
        assert response.headers["location"].endswith("#map"), response.headers
        assert browser.get("/api/cars").status_code == 200
        assert captured[0]["code_verifier"]
        import base64

        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(captured[0]["code_verifier"][0].encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        assert challenge == params["code_challenge"][0]
        assert captured[0]["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/oidc/callback"]
        assert finish_flow(browser, params).headers["location"].endswith("sso_failed")
        with connect() as db:
            assert db.execute("SELECT subject FROM auth_identities").fetchone()[0] == "idp-admin-1"
            assert db.execute("SELECT count(*) FROM auth_flows").fetchone()[0] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_email",
        "unverified",
        "audience",
        "issuer",
        "nonce",
        "expired",
        "subject_conflict",
        "disabled",
        "bad_signature",
    ],
)
def test_oidc_rejects_unapproved_or_invalid_identities(client, oidc_provider, mutation):
    settings, claims, captured = oidc_provider
    if mutation == "subject_conflict":
        with connect() as db:
            db.execute(
                "INSERT INTO auth_identities VALUES (?,?,1)",
                (settings["issuer"], "different-subject"),
            )
    if mutation == "disabled":
        with connect() as db:
            db.execute("UPDATE users SET status='disabled'")
    with TestClient(app) as browser:
        params = begin_flow(browser, claims)
        if mutation == "unknown_email":
            claims["email"] = "stranger@example.com"
        if mutation == "unverified":
            claims["email_verified"] = False
        if mutation == "audience":
            claims["aud"] = "another-app"
        if mutation == "issuer":
            claims["iss"] = "https://different.example/"
        if mutation == "nonce":
            claims["nonce"] = "wrong"
        if mutation == "expired":
            claims["exp"] = int(time.time()) - 300
        if mutation == "bad_signature":
            # Verify actual JOSE rejection, rather than bypassing the exchange or claims validator.
            wrong_key = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
            original_encode = jwt.encode

            def invalid_signature(header, payload, signing_key):
                return original_encode(header, payload, wrong_key)

            from unittest.mock import patch

            with patch.object(jwt, "encode", invalid_signature):
                assert finish_flow(browser, params).headers["location"].endswith("sso_failed")
            assert browser.get("/api/cars").status_code == 401
            return
        assert finish_flow(browser, params).headers["location"].endswith("sso_failed")
        assert browser.get("/api/cars").status_code == 401
        with connect() as db:
            assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_oidc_invited_user_activates_and_subject_binding_survives_email_change(
    client, oidc_provider
):
    _, claims, _ = oidc_provider
    client.post("/api/admin/users", json={"email": "invited@example.com"}).raise_for_status()
    claims.update(sub="invited-subject", email="invited@example.com")
    with TestClient(app) as browser:
        params = begin_flow(browser, claims)
        assert finish_flow(browser, params).headers["location"].endswith("#map")
        assert browser.get("/api/auth/session").json()["user"]["status"] == "active"
        assert browser.get("/api/admin/users").status_code == 403
        claims["email"] = "changed-at-provider@example.com"
        params = begin_flow(browser, claims)
        assert finish_flow(browser, params).headers["location"].endswith("#map")


def test_oidc_expired_flow_and_settings_change(client, oidc_provider):
    _, claims, captured = oidc_provider
    with TestClient(app) as browser:
        params = begin_flow(browser, claims)
        with connect() as db:
            db.execute("UPDATE auth_flows SET expires_at=0")
        assert finish_flow(browser, params).headers["location"].endswith("sso_failed")
        params = begin_flow(browser, claims)
        client.put("/api/admin/sso", json={"enabled": False}).raise_for_status()
        assert finish_flow(browser, params).headers["location"].endswith("sso_failed")
        assert not captured


def test_secure_cookie_on_https_and_public_json_csrf_checks(client, monkeypatch):
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Testing-password-123!"},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    monkeypatch.setattr(config, "AUTH_COOKIE_SECURE", True)
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "Testing-password-123!"}
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie


def test_environment_provider_does_not_depend_on_an_old_encrypted_configuration(
    client, monkeypatch
):
    configure_sso(client)
    (config.DATA_DIR / "auth.key").unlink()
    monkeypatch.setenv("PARKING_OIDC_ISSUER", "https://replacement.example/")
    monkeypatch.setenv("PARKING_OIDC_CLIENT_ID", "new-client")
    monkeypatch.setenv("PARKING_OIDC_CLIENT_SECRET", "new-secret")
    assert client.get("/api/admin/sso").json()["issuer"] == "https://replacement.example/"
    assert client.get("/api/auth/config").status_code == 200
