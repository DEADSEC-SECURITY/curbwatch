from copy import deepcopy

from backend.db import connect
from backend.portal import PortalError


def portal_returning(monkeypatch, tickets=None, error=None):
    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            if error:
                raise error
            return deepcopy(tickets or [])

    monkeypatch.setattr("backend.main.SyracusePortal", Portal)


def test_new_plate_requires_fresh_bound_lookup_and_no_tickets_confirmation(client):
    assert client.post("/api/cars", json={"plate": "LOCAL123"}).status_code == 422
    lookup = client.post("/api/plate-lookups", json={"plate": "local-123"})
    assert lookup.status_code == 200
    data = lookup.json()
    assert data["outcome"] == "no_tickets" and data["plate"] == "LOCAL123"
    assert client.get("/api/cars").json() == []  # Preview never saves a car.
    assert (
        client.post(
            "/api/cars",
            json={"plate": "OTHER123", "lookup_id": data["id"], "confirm_no_tickets": True},
        ).status_code
        == 422
    )
    assert (
        client.post("/api/cars", json={"plate": "LOCAL123", "lookup_id": data["id"]}).status_code
        == 422
    )
    response = client.post(
        "/api/cars", json={"plate": "LOCAL123", "lookup_id": data["id"], "confirm_no_tickets": True}
    )
    assert response.status_code == 201
    assert response.json()["verification_status"] == "user_confirmed_no_tickets"
    assert client.get("/api/cars").json()[0]["ticket_count"] == 0


def test_lookup_tickets_are_saved_atomically_with_the_new_vehicle(client, monkeypatch, raw_ticket):
    portal_returning(monkeypatch, [raw_ticket])
    lookup = client.post("/api/plate-lookups", json={"plate": "TEST123"}).json()
    assert lookup["ticket_count"] == 1
    assert client.get("/api/tickets").json() == []
    result = client.post("/api/cars", json={"plate": "TEST123", "lookup_id": lookup["id"]})
    assert result.status_code == 201
    assert result.json()["verification_status"] == "ticket_match"
    assert client.get("/api/tickets").json()[0]["ticket_number"] == "TEST001"
    assert client.get("/api/cars").json()[0]["ticket_count"] == 1
    assert (
        client.post("/api/cars", json={"plate": "TEST123", "lookup_id": lookup["id"]}).status_code
        == 409
    )


def test_expired_lookup_cannot_be_used_to_save(client):
    lookup = client.post("/api/plate-lookups", json={"plate": "LOCAL123"}).json()
    with connect() as db:
        db.execute(
            "UPDATE plate_lookups SET checked_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (lookup["id"],),
        )
    result = client.post(
        "/api/cars",
        json={"plate": "LOCAL123", "lookup_id": lookup["id"], "confirm_no_tickets": True},
    )
    assert result.status_code == 422 and "expired" in result.json()["detail"]
    assert client.get("/api/cars").json() == []


def test_portal_failure_is_not_no_tickets_and_cannot_authorize_save(client, monkeypatch):
    portal_returning(monkeypatch, error=PortalError("Portal temporarily unavailable"))
    response = client.post("/api/plate-lookups", json={"plate": "LOCAL123"})
    assert response.status_code == 503
    assert client.get("/api/cars").json() == []
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM plate_lookups").fetchone()[0] == 0


def test_wrong_plate_from_ticket_search_does_not_authorize_save(client, monkeypatch, raw_ticket):
    portal_returning(monkeypatch, [raw_ticket])
    response = client.post("/api/plate-lookups", json={"plate": "OTHER123"})
    assert response.status_code == 503 and "different license plate" in response.json()["detail"]
    assert client.get("/api/cars").json() == []
    raw_ticket.pop("plate_number")
    portal_returning(monkeypatch, [raw_ticket])
    missing = client.post("/api/plate-lookups", json={"plate": "TEST123"})
    assert missing.status_code == 503 and "did not identify" in missing.json()["detail"]


def test_paid_totals_include_fees_but_exclude_unpaid_and_dismissed_charges(
    client, monkeypatch, raw_ticket
):
    paid = deepcopy(raw_ticket)
    paid["surcharges"] = [{"amount": {"$numberDecimal": "15.00"}}]
    paid["uplifts"] = [{"amount": {"$numberDecimal": "5.00"}}]
    unpaid = deepcopy(paid)
    unpaid["ticket_number"] = "UNPAID"
    unpaid["tstatusid"] = 96
    unpaid["balance"] = {"$numberDecimal": "45.00"}
    dismissed = deepcopy(paid)
    dismissed["ticket_number"] = "DISMISSED"
    dismissed["tstatusid"] = 12
    portal_returning(monkeypatch, [paid, unpaid, dismissed])
    lookup = client.post("/api/plate-lookups", json={"plate": "TEST123"}).json()
    assert (
        client.post("/api/cars", json={"plate": "TEST123", "lookup_id": lookup["id"]}).status_code
        == 201
    )
    car = client.get("/api/cars").json()[0]
    assert car["total_spent_cents"] == 4500
    assert car["balance_cents"] == 4500
    assert car["paid_ticket_count"] == 1
    assert client.get("/api/overview").json()["total_spent_cents"] == 4500


def test_optional_contact_email_can_be_added_edited_and_cleared_without_notifications(client):
    lookup = client.post("/api/plate-lookups", json={"plate": "LOCAL123"}).json()
    body = {
        "plate": "LOCAL123",
        "lookup_id": lookup["id"],
        "confirm_no_tickets": True,
        "email": "bad-address",
    }
    assert client.post("/api/cars", json=body).status_code == 422
    body["email"] = "owner@example.com"
    response = client.post("/api/cars", json=body)
    assert response.status_code == 201
    car_id = response.json()["id"]
    assert response.json()["email"] == "owner@example.com"
    assert client.patch(f"/api/cars/{car_id}", json={"email": "not-an-email"}).status_code == 422
    assert (
        client.patch(f"/api/cars/{car_id}", json={"email": "new@example.com"}).json()["email"]
        == "new@example.com"
    )
    assert client.patch(f"/api/cars/{car_id}", json={"email": ""}).json()["email"] is None
