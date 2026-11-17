import pytest

from backend.db import connect, init_db, upsert_ticket
from backend.portal import normalize_ticket


def checked_car(client, state=None):
    lookup = client.post("/api/plate-lookups", json={"plate": "TEST123", "plate_state": state})
    assert lookup.status_code == 200
    return client.post(
        "/api/cars",
        json={
            "plate": "TEST123",
            "name": "Test car",
            "plate_state": state,
            "lookup_id": lookup.json()["id"],
            "confirm_no_tickets": True,
        },
    )


def test_state_is_optional_and_unknown_existing_vehicles_are_not_assigned_a_state(client):
    response = checked_car(client)
    assert response.status_code == 201 and response.json()["plate_state"] is None
    assert client.get("/api/cars").json()[0]["plate_state"] is None


def test_state_can_be_set_edited_and_cleared_without_changing_ticket_ownership(client, raw_ticket):
    response = checked_car(client, " ny ")
    assert response.status_code == 201 and response.json()["plate_state"] == "NY"
    car_id = response.json()["id"]
    with connect() as db:
        upsert_ticket(db, car_id, normalize_ticket(raw_ticket))
    assert client.get("/api/tickets").json()[0]["plate_state"] == "NY"
    assert (
        client.patch(f"/api/cars/{car_id}", json={"plate_state": "ma"}).json()["plate_state"]
        == "MA"
    )
    assert (
        client.patch(f"/api/cars/{car_id}", json={"name": "Renamed"}).json()["plate_state"] == "MA"
    )
    assert client.get("/api/tickets").json()[0]["plate_state"] == "MA"
    assert (
        client.patch(f"/api/cars/{car_id}", json={"plate_state": ""}).json()["plate_state"] is None
    )
    assert client.get("/api/cars").json()[0]["ticket_count"] == 1
    assert client.get("/api/tickets").json()[0]["car_id"] == car_id
    assert client.get("/api/cars").json()[0]["plate"] == "TEST123"


@pytest.mark.parametrize("invalid", ["ZZ", "New York", "<script>", 52])
def test_invalid_state_is_rejected_before_lookup_or_save(client, invalid):
    assert (
        client.post(
            "/api/plate-lookups", json={"plate": "TEST123", "plate_state": invalid}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/cars", json={"plate": "TEST123", "plate_state": invalid}).status_code
        == 422
    )
    car = checked_car(client, "NY").json()
    assert client.patch(f"/api/cars/{car['id']}", json={"plate_state": invalid}).status_code == 422
    assert client.get("/api/cars").json()[0]["plate_state"] == "NY"


def test_lookup_is_bound_to_the_selected_state_and_number(client):
    lookup = client.post(
        "/api/plate-lookups", json={"plate": "TEST123", "plate_state": "NY"}
    ).json()
    body = {
        "plate": "TEST123",
        "plate_state": "MA",
        "lookup_id": lookup["id"],
        "confirm_no_tickets": True,
    }
    response = client.post("/api/cars", json=body)
    assert response.status_code == 422 and "state changed" in response.json()["detail"]
    assert client.get("/api/cars").json() == []
    body["plate_state"] = "NY"
    assert client.post("/api/cars", json=body).status_code == 201


def test_state_is_reference_metadata_and_is_not_sent_as_a_fake_portal_filter(client, monkeypatch):
    searched = []

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            searched.append(plate)
            return []

    monkeypatch.setattr("backend.main.SyracusePortal", Portal)
    response = checked_car(client, "DC")
    assert response.status_code == 201 and response.json()["plate_state"] == "DC"
    assert searched == ["TEST123"]


def test_additive_state_migration_is_repeatable_and_preserves_records(client, raw_ticket):
    car_id = checked_car(client, "VA").json()["id"]
    with connect() as db:
        upsert_ticket(db, car_id, normalize_ticket(raw_ticket))
        # Reproduce a pre-feature database without rebuilding parent/child tables.
        db.execute("ALTER TABLE cars DROP COLUMN plate_state")
        db.execute("ALTER TABLE plate_lookups DROP COLUMN plate_state")
    init_db(seed=False)
    init_db(seed=False)
    cars = client.get("/api/cars").json()
    assert len(cars) == 1 and cars[0]["id"] == car_id
    assert cars[0]["plate_state"] is None and cars[0]["ticket_count"] == 1
    with connect() as db:
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert (
        client.patch(f"/api/cars/{car_id}", json={"plate_state": "PR"}).json()["plate_state"]
        == "PR"
    )
