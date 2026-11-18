# Optional vehicle plate state

`CarCreate`, `CarUpdate` and `PlateLookup` accept optional `plate_state`.
Use a two-letter US state/DC/territory code from `backend/resources/plate-states.json`.
Whitespace/case is normalized; blank or null means "Not set". Unknown codes -> 422.

`GET /api/cars`, car create/edit responses, and private `GET /api/tickets` return
the vehicle's `plate_state`. PATCH omission preserves it; null/blank clears it.
Existing cars start unset; an additive migration retains ids and ticket ownership.
The registration state is user-entered metadata, never inferred from OCR.

The Syracuse portal search form accepts a plate number without a state filter.
State is stored for reference, not claimed as a state-specific registration or
ticket verification. Current duplicate protection still uses the plate number.
Pre-save lookup tokens bind to the reviewed plate and selected state; changing
either requires another lookup. Existing unspecified-state clients remain valid.

Shared map responses continue to exclude all vehicle fields, including plate state.

## Cars and data plates

`GET /api/cars` and create/edit responses include `record_type`: `vehicle` (a car
with optional name/contact) or `plate` (data collection only). Existing records are
migrated to `vehicle`; ids, tickets and monitoring schedules are preserved.
`CarCreate` defaults to `vehicle`; `CarUpdate` can promote a data plate by setting
`record_type: "vehicle"` along with its name/email. Data plates cannot have contact
emails. Both kinds continue to collect tickets and contribute to map aggregates.

`POST /api/plates` accepts only `{plate, plate_state}` with state defaulting to `NY`.
It normalizes and validates both fields, performs the same successful source lookup,
and atomically saves the data plate and its initial tickets, returning 201. The save
action confirms the typed text even if the source returns no tickets. No separate
lookup/review request or owner information is needed. Invalid input -> 422;
duplicate plate text -> 409; source/validation failure -> 503 with nothing saved;
another lookup running -> 429. Authentication, JSON, same-origin and CSRF protections
match car creation. Initial history does not send notifications. Data plates have no
recipient and send no email notifications; adding car details enables normal email
behavior for future tickets when SMTP is configured.
