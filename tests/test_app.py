from copy import deepcopy
from datetime import date
import json

from backend.activity import activity
from backend.collector import collect, reserve_run
from backend.db import connect, upsert_ticket
from backend.portal import normalize_ticket


def add_car(client):
    lookup = client.post("/api/plate-lookups", json={"plate": "test-123"}).json()
    response = client.post(
        "/api/cars",
        json={
            "name": "Test car",
            "plate": "test-123",
            "lookup_id": lookup["id"],
            "confirm_no_tickets": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_plate_normalization_duplicate_and_pause_preserves_history(client, raw_ticket):
    car_id = add_car(client)
    assert client.get("/api/cars").json()[0]["plate"] == "TEST123"
    assert client.post("/api/cars", json={"plate": "TEST 123"}).status_code == 409
    assert client.post("/api/cars", json={"plate": "<script>"}).status_code == 422
    with connect() as db:
        upsert_ticket(db, car_id, normalize_ticket(raw_ticket))
    assert client.patch(f"/api/cars/{car_id}", json={"active": False}).status_code == 200
    assert client.get("/api/cars").json()[0]["ticket_count"] == 1
    assert client.get("/api/overview").json()["active_cars"] == 0
    assert len(client.get("/api/tickets").json()) == 1


def test_other_website_cannot_modify_local_data(client):
    response = client.post(
        "/api/cars", json={"plate": "BAD123"}, headers={"Origin": "https://unrelated.example"}
    )
    assert response.status_code == 403
    assert client.get("/api/cars").json() == []


def test_repeated_checks_update_all_financial_fields_without_duplicate_events(client, raw_ticket):
    add_car(client)
    payload = deepcopy(raw_ticket)

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            return [deepcopy(payload)]

    run_id, _ = reserve_run()
    collect(run_id, Portal, delay=0)
    run_id, _ = reserve_run()
    collect(run_id, Portal, delay=0)
    assert len(client.get("/api/tickets").json()) == 1
    payload["violation"]["amount"]["$numberDecimal"] = "30.00"
    payload["surcharges"] = [{"amount": {"$numberDecimal": "15.00"}}]
    payload["balance"]["$numberDecimal"] = "45.00"
    payload["tstatusid"] = 16
    run_id, _ = reserve_run()
    collect(run_id, Portal, delay=0)
    ticket = client.get("/api/tickets").json()[0]
    assert (ticket["fine_cents"], ticket["surcharge_cents"], ticket["balance_cents"]) == (
        3000,
        1500,
        4500,
    )
    assert ticket["status_id"] == 16
    assert len(client.get(f"/api/tickets/{ticket['id']}/changes").json()) == 1
    assert client.get("/api/checks").json()[0]["updated_tickets"] == 1


def test_bad_ticket_rolls_back_the_car_and_records_failure(client, raw_ticket):
    add_car(client)

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def search(self, plate):
            return [raw_ticket, {"plate_number": plate}]

    run_id, _ = reserve_run()
    collect(run_id, Portal, delay=0)
    assert client.get("/api/tickets").json() == []
    assert client.get("/api/cars").json()[0]["last_error"]
    assert client.get("/api/checks").json()[0]["status"] == "failed"


def test_reservation_blocks_overlaps_and_recovers_stale_runs(client):
    add_car(client)
    run_id, created = reserve_run()
    same_id, created_again = reserve_run()
    assert created and not created_again and run_id == same_id
    with connect() as db:
        db.execute(
            "UPDATE check_runs SET requested_at='2000-01-01T10:00:00+00:00' WHERE id=?", (run_id,)
        )
    new_id, created = reserve_run()
    assert created and new_id != run_id


def test_import_is_atomic_and_legacy_time_does_not_influence_hourly_estimates(client):
    car_id = add_car(client)
    rows = [
        {
            "Ticket Number": "OLD1",
            "Issue Date": "2024-11-04 10:30:00",
            "Location Name": "WAVERLY AVE",
            "Fine": "25",
        }
    ]
    request = {"format": "json", "car_id": car_id, "content": json.dumps(rows + [{"Fine": "25"}])}
    assert client.post("/api/import", json=request).status_code == 422
    assert client.get("/api/tickets").json() == []
    request["content"] = json.dumps(rows)
    assert client.post("/api/import", json=request).json()["new_tickets"] == 1
    result = client.get("/api/activity?day=2026-11-16&hour=10").json()
    assert result["unverified_tickets"] == 1
    assert sum(result["hourly_counts"]) == 0


def test_legacy_import_does_not_overwrite_live_data(client, raw_ticket):
    car_id = add_car(client)
    with connect() as db:
        upsert_ticket(db, car_id, normalize_ticket(raw_ticket))
    rows = [{"Ticket Number": "TEST001", "Issue Date": "2024-11-04 11:00:00", "Fine": "999"}]
    response = client.post(
        "/api/import", json={"format": "json", "car_id": car_id, "content": json.dumps(rows)}
    )
    assert response.status_code == 200
    assert client.get("/api/tickets").json()[0]["fine_cents"] == 2500


def test_unknown_sparse_future_and_unverified_observations_stay_out_of_estimates(raw_ticket):
    ticket = normalize_ticket(raw_ticket)
    result = activity([ticket], date(2026, 11, 16), 9, 0)
    assert result["streets"][0]["score"] is None
    assert result["streets"][0]["level"] == "insufficient"
    assert len(result["features"]) > 0
    result = activity([ticket], date(2020, 1, 1), 9)
    assert not result["streets"] and not sum(result["hourly_counts"])


def test_direct_issue_time_is_used_instead_of_surcharge_date(raw_ticket):
    raw_ticket["surcharges"] = [
        {
            "issue_date": {"$date": {"$numberLong": "1762266600000"}},
            "amount": {"$numberDecimal": "15"},
        }
    ]
    ticket = normalize_ticket(raw_ticket)
    assert ticket["issued_at"].startswith("2024-11-04")
    assert ticket["surcharge_cents"] == 1500
    assert ticket["fine_cents"] == 2500


def test_detail_response_preserves_multiple_violations_and_source_status(raw_ticket):
    violation = raw_ticket.pop("violation")
    raw_ticket["violations"] = [
        violation,
        {**deepcopy(violation), "amount": {"$numberDecimal": "60.00"}},
    ]
    raw_ticket["tstatusid"] = 96
    raw_ticket["status"] = {"display_text": "Awaiting payment"}
    ticket = normalize_ticket(raw_ticket)
    assert ticket["fine_cents"] == 8500
    assert ticket["description"] == "Parking violation"
    assert ticket["status"] == "Awaiting payment"
