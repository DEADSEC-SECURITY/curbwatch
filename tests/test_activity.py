from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.activity import activity

TODAY = date(2026, 11, 16)
NY = ZoneInfo("America/New_York")


def ticket(age, hour=16, street="WAVERLY AVE", **updates):
    issued = datetime.combine(TODAY - timedelta(days=age), datetime.min.time(), NY)
    return {
        "issued_at": issued.replace(hour=hour).isoformat(),
        "time_source": "ticket_issue_date",
        "street_key": street,
        "location_name": street,
        **updates,
    }


def test_defaults_to_ninety_days_and_bars_use_the_same_period():
    records = [ticket(age, 9) for age in (100, 101, 102)] + [ticket(age) for age in (1, 2, 3)]
    result = activity(records, TODAY, 16)
    assert result["period"]["history_days"] == 90
    assert result["period"]["ticket_count"] == 3
    assert result["hourly_counts"][9] == 0
    assert result["hourly_counts"][16] == 3
    assert result["streets"][0]["level"] == "high"
    assert result["streets"][0]["score"] == 1
    assert result["streets"][0]["total_tickets"] == 6
    assert result["streets"][0]["period_tickets"] == 3
    assert "weighting" not in result and "hourly_weighted" not in result


def test_old_and_new_tickets_count_equally_in_the_selected_period():
    records = [ticket(age) for age in (1, 30, 150)] + [ticket(age, 9) for age in (2, 31, 151)]
    result = activity(records, TODAY, 16, 180)
    street = result["streets"][0]
    assert street["score"] == 0.5
    assert street["tickets_per_observed_day"] == 0.5
    assert street["observed_days"] == 6 and street["distinct_days"] == 3
    assert street["sample_tickets"] == 3
    assert result["hourly_counts"][16] == result["hourly_counts"][9] == 3
    # Shift the whole sample earlier within the same window: the frequency is identical.
    earlier = activity(
        [ticket(age) for age in (31, 60, 170)] + [ticket(age, 9) for age in (32, 61, 171)],
        TODAY,
        16,
        180,
    )
    assert earlier["streets"][0]["score"] == 0.5


@pytest.mark.parametrize("days", [7, 30, 90, 180, 365])
def test_inclusive_period_boundaries_have_exact_number_of_days(days):
    result = activity([ticket(0), ticket(days - 1), ticket(days)], TODAY, 16, days)
    assert result["period"]["ticket_count"] == 2
    assert result["period"]["start"] == (TODAY - timedelta(days=days - 1)).isoformat()
    assert sum(result["hourly_counts"]) == 2


def test_all_history_includes_old_samples_but_never_future_days():
    result = activity([ticket(800), ticket(900), ticket(1000), ticket(-1)], TODAY, 16, 0)
    assert result["period"]["all_history"] is True
    assert result["period"]["start"] == (TODAY - timedelta(days=1000)).isoformat()
    assert result["period"]["ticket_count"] == 3
    assert result["streets"][0]["score"] == 1
    assert result["hourly_counts"][16] == 3


def test_exact_hour_only_and_no_hidden_weekday_preference():
    records = [ticket(age) for age in (0, 7, 14, 1, 2, 3)] + [ticket(4, 15), ticket(5, 17)]
    street = activity(records, TODAY, 16)["streets"][0]
    assert street["sample_tickets"] == 6
    assert street["distinct_days"] == 6
    assert street["observed_days"] == 8
    assert street["score"] == 0.75
    assert street["basis"] == "Exact hour, all weekdays; every ticket counts equally"


def test_same_day_duplicates_increase_ticket_average_without_inflating_day_frequency():
    records = [ticket(1), ticket(1), ticket(2)] + [ticket(age, 9) for age in (1, 3, 4)]
    street = activity(records, TODAY, 16)["streets"][0]
    assert street["sample_tickets"] == 3
    assert street["distinct_days"] == 2
    assert street["observed_days"] == 4
    assert street["score"] == 0.5
    assert street["tickets_per_observed_day"] == 0.75


def test_sparse_samples_are_visible_without_claiming_a_reliable_score():
    street = activity([ticket(1), ticket(20, 9)], TODAY, 16)["streets"][0]
    assert street["observed_day_fraction"] == 0.5
    assert street["sample_tickets"] == 1
    assert street["score"] is None and street["level"] == "insufficient"
    no_hour = activity([ticket(1, 9)], TODAY, 16)["streets"][0]
    assert no_hour["sample_tickets"] == 0
    assert no_hour["observed_day_fraction"] == 0


def test_past_date_uses_its_own_lookback_and_hides_later_observations():
    result = activity([ticket(40, 9), ticket(31), ticket(1)], TODAY - timedelta(days=30), 16, 7)
    assert sum(result["hourly_counts"]) == 1
    assert result["period"]["ticket_count"] == 1
    assert result["streets"][0]["last_ticket_at"] == ticket(31)["issued_at"]


def test_unverified_and_undated_cannot_influence_highlights():
    result = activity(
        [ticket(1), ticket(1, time_source="legacy_surcharge"), ticket(1, issued_at=None)], TODAY, 16
    )
    assert result["unverified_tickets"] == 1 and result["undated_tickets"] == 1
    assert result["period"]["ticket_count"] == 1
    assert result["hourly_counts"][16] == 1


def test_api_validates_period_and_leaves_history_untouched(client, raw_ticket):
    from backend.db import connect, upsert_ticket
    from backend.portal import normalize_ticket

    lookup = client.post("/api/plate-lookups", json={"plate": "TEST123"}).json()
    car = client.post(
        "/api/cars",
        json={"plate": "TEST123", "lookup_id": lookup["id"], "confirm_no_tickets": True},
    ).json()
    normalized = normalize_ticket(raw_ticket)
    normalized.update(ticket(150))
    with connect() as db:
        upsert_ticket(db, car["id"], normalized)
    url = f"/api/activity?day={TODAY}&hour=16&car_id={car['id']}"
    assert client.get(url).json()["period"]["ticket_count"] == 0
    assert client.get(url + "&history_days=180").json()["period"]["ticket_count"] == 1
    assert client.get(url + "&history_days=0").json()["period"]["all_history"] is True
    assert client.get(url + "&history_days=999").status_code == 422
    assert len(client.get("/api/tickets").json()) == 1
