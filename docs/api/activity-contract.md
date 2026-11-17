# Selectable map history

Both GET `/api/activity` (account session required) and GET `/api/shared/activity` (restricted bearer token required) accept `day`, `hour` and `history_days`. The private route additionally supports `car_id`; shared maps reject vehicle filtering.

`history_days` is 7,30,90,180,365 or 0. Default 90 corresponds to three months; 0 selects all verified history up to the chosen date. Windows include the end date and exactly N calendar dates in America/New_York; observations after that date are excluded. Invalid periods return HTTP 422. Period, hour and vehicle changes are read-only.

Response `period`: history_days,start,end,ticket_count,all_history. `hourly_counts` contains 24 unweighted exact-hour totals for the selected period. Former `weighting`, `hourly_weighted` and automatic new-hour signals are removed. No age, nearby-hour or weekday weights are used.

Street summaries retain lifetime-to-selected-date `total_tickets` for context and add selected `period_tickets`, `observed_days`, `observed_day_fraction` and `tickets_per_observed_day`. `sample_tickets` and `distinct_days` concern the exact selected hour. Frequency = distinct sampled dates at this hour / all sampled ticketed dates on that street within the period. Duplicate tickets on one date do not inflate the date frequency. Score equals that fraction only when the hour has at least 3 tickets on at least 2 dates; otherwise null, insufficient/blue dashed if any samples, gray if none. Thresholds low<.25, moderate<.6, high>=.6. This index describes the sample, not patrol probability or a denominator of actual parked days.

Shared responses allowlist aggregate fields and geometry only. They never return license plates, emails, user records, car IDs, individual ticket rows or exact issue timestamps. Period/date changes cannot bypass restricted-link expiry/revocation.
