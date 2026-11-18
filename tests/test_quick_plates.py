from copy import deepcopy

import pytest

from backend.collector import collect, reserve_run
from backend.db import connect, init_db
from backend.portal import PortalError
from test_plate_lookup import portal_returning


def test_quick_plate_defaults_to_ny_normalizes_and_is_separate_from_cars(client):
    response = client.post("/api/plates", json={"plate": "data-123"})
    assert response.status_code == 201
    plate = response.json()
    assert (plate["plate"], plate["plate_state"], plate["record_type"]) == (
        "DATA123",
        "NY",
        "plate",
    )
    assert plate["email"] is None
    assert plate["active"] == 1
    assert plate["last_success_at"]
    assert client.get("/api/cars").json()[0]["record_type"] == "plate"
    assert client.post("/api/plates", json={"plate": "DATA 123"}).status_code == 409
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 1


def test_quick_plate_saves_verified_history_and_continues_collecting_without_email(
    client, monkeypatch, raw_ticket
):
    portal_returning(monkeypatch, [raw_ticket])
    result = client.post("/api/plates", json={"plate": "TEST123", "plate_state": "NJ"})
    assert result.status_code == 201
    assert result.json()["plate_state"] == "NJ"
    assert result.json()["verification_status"] == "ticket_match"
    assert len(client.get("/api/tickets").json()) == 1

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            ticket = deepcopy(raw_ticket)
            ticket["ticket_number"] = "NEW-DATA-TICKET"
            return [ticket]

    run_id, _ = reserve_run()
    monkeypatch.setattr(
        "backend.collector.notification_policy",
        lambda: {
            "enabled": True,
            "ticket_alerts": True,
        },
    )
    collect(run_id, Portal, delay=0)
    assert len(client.get("/api/tickets").json()) == 2
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM email_outbox").fetchone()[0] == 0


@pytest.mark.parametrize("failure", [PortalError("Unavailable"), ValueError("Wrong plate")])
def test_quick_plate_failure_never_saves_a_record(client, monkeypatch, failure):
    portal_returning(monkeypatch, error=failure)
    assert client.post("/api/plates", json={"plate": "DATA123"}).status_code == 503
    assert client.get("/api/cars").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"plate": "<bad>"},
        {"plate": "DATA123", "plate_state": "ZZ"},
        {"plate": "DATA123", "plate_state": None},
        {"plate": "DATA123", "email": "owner@example.com"},
    ],
)
def test_quick_plate_validates_input(client, body):
    assert client.post("/api/plates", json=body).status_code == 422
    assert client.get("/api/cars").json() == []


def test_data_plate_can_become_a_car_without_losing_history(client, monkeypatch, raw_ticket):
    portal_returning(monkeypatch, [raw_ticket])
    plate = client.post("/api/plates", json={"plate": "TEST123"}).json()
    tickets = client.get("/api/tickets").json()
    assert len(tickets) == 1
    assert (
        client.patch(f"/api/cars/{plate['id']}", json={"email": "friend@example.com"}).status_code
        == 422
    )
    response = client.patch(
        f"/api/cars/{plate['id']}",
        json={"record_type": "vehicle", "name": "Friend’s car", "email": "friend@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["record_type"] == "vehicle"
    assert response.json()["id"] == plate["id"]
    assert response.json()["email"] == "friend@example.com"
    assert response.json()["last_success_at"] == plate["last_success_at"]
    assert client.get("/api/tickets").json()[0]["id"] == tickets[0]["id"]


def test_existing_database_records_remain_cars(database):
    with connect() as db:
        db.execute("ALTER TABLE cars DROP COLUMN record_type")
        db.execute(
            "INSERT INTO cars(name,plate,created_at) VALUES ('Existing','OLD123','2026-01-01')"
        )
    init_db(seed=False)
    init_db(seed=False)
    with connect() as db:
        assert db.execute("SELECT record_type FROM cars").fetchone()[0] == "vehicle"


def test_data_plates_are_not_reported_as_cars_missing_a_notification_email(client):
    plate = client.post("/api/plates", json={"plate": "DATA123"}).json()
    assert client.get("/api/admin/email").json()["missing_recipient_vehicles"] == 0
    assert (
        client.patch(f"/api/cars/{plate['id']}", json={"record_type": "vehicle"}).status_code == 200
    )
    assert client.get("/api/admin/email").json()["missing_recipient_vehicles"] == 1
