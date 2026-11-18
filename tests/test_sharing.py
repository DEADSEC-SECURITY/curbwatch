from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from backend.db import connect, now, upsert_ticket
from backend.portal import normalize_ticket
from backend.shared import app as shared_app


@pytest.fixture
def viewer(database):
    with TestClient(shared_app) as client:
        yield client


def create_link(client, **body):
    response = client.post("/api/shares", json=body)
    assert response.status_code == 201
    data = response.json()
    token = urlsplit(data["url"]).fragment
    return data, {"Authorization": f"Bearer {token}"}


def test_link_secret_is_only_returned_once_and_stored_as_a_hash(client, viewer):
    link, headers = create_link(client)
    token = headers["Authorization"].split()[1]
    assert len(token) == 43
    assert link["status"] == "active"
    assert urlsplit(link["url"]).path == "/share/"
    assert not urlsplit(link["url"]).query
    assert client.post("/api/shares", json={}).json()["url"] != link["url"]
    with connect() as db:
        row = dict(db.execute("SELECT * FROM map_shares WHERE id=?", (link["id"],)).fetchone())
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(row)
    listing = client.get("/api/shares")
    assert token not in listing.text and row["token_hash"] not in listing.text
    assert "url" not in listing.json()["links"][0]
    assert listing.headers["cache-control"] == "no-store"
    assert viewer.get("/api/shared/activity", headers=headers).status_code == 200


def test_viewer_only_receives_aggregates_and_never_car_or_ticket_details(
    client, viewer, raw_ticket
):
    with connect() as db:
        car_id = db.execute(
            "INSERT INTO cars(name,plate,email,created_at) VALUES (?,?,?,?)",
            ("PRIVATE_OWNER_NAME", "PRIVATE123", "private-owner@example.com", now()),
        ).lastrowid
        for index in range(3):
            raw = deepcopy(raw_ticket)
            raw.update(
                {
                    "ticket_number": f"PRIVATE_TICKET_{index}",
                    "plate_number": "PRIVATE123",
                    "issue_date": {
                        "$date": {
                            "$numberLong": str(
                                int(
                                    (datetime.now(timezone.utc) - timedelta(days=index)).timestamp()
                                    * 1000
                                )
                            )
                        }
                    },
                }
            )
            raw["violation"]["type"]["display_text"] = "PRIVATE_VIOLATION"
            upsert_ticket(db, car_id, normalize_ticket(raw))
    _, headers = create_link(client)
    response = viewer.get("/api/shared/activity?hour=16", headers=headers)
    assert response.status_code == 200
    assert response.json()["streets"][0]["total_tickets"] == 3
    assert response.json()["features"]
    assert "PRIVATE" not in response.text
    forbidden = {
        "plate",
        "plate_state",
        "car_id",
        "car_name",
        "email",
        "ticket_number",
        "ticket_id",
        "raw_payload",
        "issued_at",
        "last_ticket_at",
        "balance_cents",
        "fine_cents",
        "last_error",
    }

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(response.json())
    assert viewer.get("/api/shared/streets", headers=headers).json()["features"]
    assert client.get("/api/cars").json()[0]["email"] == "private-owner@example.com"
    assert len(client.get("/api/tickets").json()) == 3


@pytest.mark.parametrize(
    "path",
    [
        "/api/cars",
        "/api/tickets",
        "/api/tickets/1/changes",
        "/api/overview",
        "/api/checks",
        "/api/shares",
        "/api/plate-lookups",
        "/api/plates",
        "/api/activity",
        "/api/streets",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/sw.js",
        "/manifest.webmanifest",
        "/",
        "/index.html",
    ],
)
def test_valid_shared_link_does_not_open_private_routes(client, viewer, path):
    _, headers = create_link(client)
    assert viewer.get(path, headers=headers).status_code == 404


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/cars", "post"),
        ("/api/cars/1", "patch"),
        ("/api/checks", "post"),
        ("/api/import", "post"),
        ("/api/plate-lookups", "post"),
        ("/api/plates", "post"),
        ("/api/shares", "post"),
        ("/api/shares/anything/revoke", "post"),
        ("/api/shared/activity", "post"),
        ("/api/shared/streets", "post"),
    ],
)
def test_viewers_cannot_write_even_with_a_valid_link(client, viewer, path, method):
    _, headers = create_link(client)
    response = getattr(viewer, method)(path, headers=headers, json={"plate": "BAD123"})
    assert response.status_code in (404, 405)
    assert client.get("/api/cars").json() == []


def test_missing_malformed_tampered_and_unknown_tokens_have_the_same_failure(client, viewer):
    _, headers = create_link(client)
    token = headers["Authorization"].split()[1]
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    cases = [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer short"},
        {"Authorization": f"Basic {token}"},
        {"Authorization": "Bearer " + "A" * 43},
        {"Authorization": f"Bearer {tampered}"},
    ]
    failures = [viewer.get("/api/shared/activity", headers=value) for value in cases]
    assert {response.status_code for response in failures} == {404}
    assert len({response.text for response in failures}) == 1
    assert viewer.get("/api/shared/streets").status_code == 404
    assert viewer.get("/api/shared/activity?hour=garbage").status_code == 404


def test_revoke_is_idempotent_and_stops_an_existing_view_without_affecting_other_links(
    client, viewer
):
    first, headers = create_link(client, name="Friends")
    _, other_headers = create_link(client, name="Other friends")
    assert viewer.get("/api/shared/activity", headers=headers).status_code == 200
    response = client.post(f"/api/shares/{first['id']}/revoke")
    assert response.json()["status"] == "revoked"
    assert client.post(f"/api/shares/{first['id']}/revoke").json() == response.json()
    assert viewer.get("/api/shared/activity", headers=headers).status_code == 404
    assert viewer.get("/api/shared/streets", headers=headers).status_code == 404
    assert viewer.get("/api/shared/activity", headers=other_headers).status_code == 200
    assert client.post("/api/shares/not-found/revoke").status_code == 404


def test_expiry_is_checked_on_every_request_and_does_not_reactivate_expired_links(client, viewer):
    link, headers = create_link(client, expires_in_days=7)
    assert viewer.get("/api/shared/activity", headers=headers).status_code == 200
    with connect() as db:
        db.execute(
            "UPDATE map_shares SET expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), link["id"]),
        )
    assert viewer.get("/api/shared/activity", headers=headers).status_code == 404
    assert viewer.get("/api/shared/streets", headers=headers).status_code == 404
    assert client.get("/api/shares").json()["links"][0]["status"] == "expired"


def test_viewer_response_headers_and_query_limits(client, viewer):
    _, headers = create_link(client, expires_in_days=None)
    assert client.get("/api/shares").json()["links"][0]["expires_at"] is None
    for path in ("/share/", "/api/shared/activity", "/api/shared/streets"):
        response = viewer.get(path, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-robots-tag"] == "noindex, nofollow"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    for query in ("hour=24", "hour=-1", "day=not-a-date"):
        assert viewer.get(f"/api/shared/activity?{query}", headers=headers).status_code == 422
    assert viewer.get("/api/shared/activity?car_id=1", headers=headers).status_code == 400
    assert (
        viewer.get("/api/shared/activity?day=2024-11-01&hour=4", headers=headers).json()["hour"]
        == 4
    )
    assert client.post("/api/shares", json={"expires_in_days": -1}).status_code == 422
    assert client.post("/api/shares", json={"name": "x" * 81}).status_code == 422
    assert (
        client.post(
            "/api/shares", json={}, headers={"Origin": "https://unrelated.example"}
        ).status_code
        == 403
    )


def test_shared_entry_has_separate_installation_without_owner_bundle(client, viewer):
    response = viewer.get("/share/")
    assert response.status_code == 200
    assert "<title>Shared map · Curbwatch</title>" in response.text
    assert 'id="shared-manifest"' in response.text
    assert "apple-mobile-web-app-capable" in response.text
    assert "owner-" not in response.text
    worker = viewer.get("/share/sw.js")
    assert worker.status_code == 200
    assert "application/javascript" in worker.headers["content-type"]
    assert "caches." not in worker.text
    assert "/index.html" not in worker.text
    assert viewer.get("/icons/icon-192.png").status_code == 200
    assert viewer.get("/icons/icon-512.png").status_code == 200
    assert "/api/shared/activity" not in client.get("/openapi.json").text


def test_shared_period_control_uses_same_unweighted_model_without_private_rows(
    client, viewer, raw_ticket
):
    link, headers = create_link(client)
    from backend.activity import NY
    from datetime import datetime, timedelta

    with connect() as db:
        car_id = db.execute(
            "INSERT INTO cars(name,plate,created_at) VALUES (?,?,?)", ("PRIVATE", "PRIV123", now())
        ).lastrowid
        raw = deepcopy(raw_ticket)
        raw["plate_number"] = "PRIV123"
        normalized = normalize_ticket(raw)
        issued = datetime.now(NY) - timedelta(days=150)
        normalized["issued_at"] = issued.isoformat()
        upsert_ticket(db, car_id, normalized)
    default = viewer.get("/api/shared/activity", headers=headers)
    six_months = viewer.get("/api/shared/activity?history_days=180", headers=headers)
    assert default.json()["period"]["ticket_count"] == 0
    assert six_months.json()["period"]["ticket_count"] == 1
    assert sum(six_months.json()["hourly_counts"]) == 1
    assert "weighting" not in six_months.json()
    assert "PRIVATE" not in six_months.text and "PRIV123" not in six_months.text
    assert viewer.get("/api/shared/activity?history_days=0", headers=headers).json()["period"][
        "all_history"
    ]
    assert viewer.get("/api/shared/activity?history_days=5", headers=headers).status_code == 422
    assert viewer.get("/api/shared/activity?history_days=180").status_code == 404
