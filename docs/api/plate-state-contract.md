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
