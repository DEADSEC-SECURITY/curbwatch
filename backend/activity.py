"""Unweighted ticket-day frequencies within an explicitly selected history period."""

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal, Annotated
from pydantic import BeforeValidator

from .config import TIMEZONE, DEFAULT_HISTORY_DAYS
from .streets import matched_key, street_index

NY = ZoneInfo(TIMEZONE)
HistoryDays = Annotated[Literal[0, 7, 30, 90, 180, 365], BeforeValidator(int)]


def activity(tickets, selected_date, hour, history_days=DEFAULT_HISTORY_DAYS):
    if history_days not in (0, 7, 30, 90, 180, 365):
        raise ValueError("Choose a supported history period.")
    start = selected_date - timedelta(days=history_days - 1) if history_days else None
    grouped = defaultdict(list)
    hourly = [0] * 24
    undated = unmapped = unverified = eligible = 0
    earliest = None
    for ticket in tickets:
        if not ticket["issued_at"]:
            undated += 1
            continue
        if ticket.get("time_source") != "ticket_issue_date":
            unverified += 1
            continue
        issued = datetime.fromisoformat(ticket["issued_at"]).astimezone(NY)
        # Exploring the past never includes later days, including in all-history mode.
        if issued.date() > selected_date:
            continue
        earliest = min(earliest, issued.date()) if earliest else issued.date()
        included = start is None or issued.date() >= start
        if included:
            hourly[issued.hour] += 1
            eligible += 1
        key = matched_key(ticket["street_key"])
        if not key and included:
            unmapped += 1
        grouped[key or ticket["street_key"]].append((ticket, issued, included))
    summaries, features = [], []
    for key, records in grouped.items():
        current = [(ticket, issued) for ticket, issued, included in records if included]
        samples = [(ticket, issued) for ticket, issued in current if issued.hour == hour]
        sample_days = len({issued.date() for _, issued in samples})
        observed_days = len({issued.date() for _, issued in current})
        frequency = sample_days / observed_days if observed_days else None
        enough = len(samples) >= 3 and sample_days >= 2
        score = frequency if enough else None
        level = (
            "insufficient"
            if score is None
            else ("high" if score >= 0.6 else "moderate" if score >= 0.25 else "low")
        )
        summary = {
            "street_key": key,
            "name": records[0][0]["location_name"],
            "total_tickets": len(records),
            "period_tickets": len(current),
            "sample_tickets": len(samples),
            "distinct_days": sample_days,
            "observed_days": observed_days,
            "observed_day_fraction": round(frequency, 3) if frequency is not None else None,
            "tickets_per_observed_day": round(len(samples) / observed_days, 3)
            if observed_days
            else None,
            "score": round(score, 3) if score is not None else None,
            "level": level,
            "confidence": "moderate" if enough else "limited",
            "basis": "Exact hour, all weekdays; every ticket counts equally",
            "last_ticket_at": max(issued for _, issued, _ in records).isoformat(),
            "mapped": key in street_index(),
            "precision": "street",
        }
        summaries.append(summary)
        for feature in street_index().get(key, []):
            features.append({**feature, "properties": {**feature["properties"], **summary}})
    summaries.sort(
        key=lambda value: (
            value["score"] if value["score"] is not None else -1,
            value["sample_tickets"],
            value["period_tickets"],
            value["total_tickets"],
        ),
        reverse=True,
    )
    period_start = start or earliest or selected_date
    return {
        "type": "FeatureCollection",
        "features": features,
        "streets": summaries,
        "hourly_counts": hourly,
        "undated_tickets": undated,
        "unmapped_tickets": unmapped,
        "unverified_tickets": unverified,
        "date": selected_date.isoformat(),
        "hour": hour,
        "timezone": TIMEZONE,
        "period": {
            "history_days": history_days,
            "start": period_start.isoformat(),
            "end": selected_date.isoformat(),
            "ticket_count": eligible,
            "all_history": history_days == 0,
        },
        "model": "Unweighted fraction of a street’s ticketed days with a ticket in the exact selected hour. "
        "Only the selected history period is used. Not officer-presence probability.",
    }
