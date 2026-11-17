# User guide

## Garage and tickets

Add vehicles manually or scan a photo/live camera view. Review the exact plate, optional state, name and email. Every new plate must pass a successful ticket-source lookup before saving; zero matches require confirming the text. A no-ticket result is not registration validation. The Syracuse adapter searches by plate text, not state, and duplicate protection uses that text.

Initial tickets save atomically with the car. The reviewed lookup expires after ten minutes by default. Changing the plate or state invalidates it. Failures are never treated as empty results. Pausing a vehicle preserves its history; manually checking a paused vehicle is still possible.

Vehicle cards separate outstanding balance from total spent. “Total spent” sums recorded charges for tickets marked Paid in full; the source does not provide a complete transaction/partial-payment ledger. Ticket history includes paid/dismissed records and status/balance changes.

Import CSV or JSON from Ticket history. Use a License Plate column or select a vehicle. Imports are atomic; invalid rows roll back the file. Legacy timestamps remain unverified until a live lookup supplies a direct issue date, and imports do not overwrite more authoritative portal data.

## Street activity

The default is the current configured timezone/hour and the last 90 days. Choose 7/30/90/180/365 days or All history. The selected date is the inclusive end of the window; future days are excluded. Counts in the timeline and map use the same period, exact hour and equal ticket weights. Changing the history window never deletes tickets.

The activity index is the fraction of a street's ticketed dates with at least one ticket in the selected hour. Low is below 25%, moderate below 60%, high at least 60%. A color score needs three exact-hour tickets across two dates. Sparse samples are blue dashed; gray means no exact-hour sample in the selected period. We do not know where cars were parked on days without tickets, so this is not a calibrated probability of officer presence.

Play loops 24 hour blocks at one- or two-second intervals and waits for each result. Manual period/date/car changes, dialogs, hidden tabs and navigation pause playback. Selection stays on the same street while hours change. Desktop map layouts fit the available window; long street lists/details scroll inside their panel. Phones use normal page flow.

Locations identify streets, often multiple blocks; they do not identify exact patrol locations. Unmatched places are listed without invented coordinates. Background maps and the ticket portal need internet; downloaded road geometry is cached locally.

## Emails, accounts and sharing

A vehicle's optional email receives its new-ticket alerts and monthly outstanding summary after SMTP is enabled. Reports group that person's cars, including paused vehicles, and include every positive balance regardless of issue month. See [email behavior](email.md) for schedule, catch-up and retry details. Initial/imported history does not generate a batch of alerts.

Admins add/invite users in Settings. There is no public signup or automatic SSO enrollment. Users share the garage; admins also manage access, SMTP, OIDC and share links. Invitations are copied for private delivery rather than emailed automatically.

Share map creates an expiring, revocable link to the map/timeline only. Plates, emails, tickets, balances and all management controls remain private. Full link secrets appear only at creation and cannot be retrieved later. Keep and distribute the copied link appropriately.

## Camera, PWA and offline use

OCR runs locally with bundled Tesseract workers/models. No photos or videos go to a cloud OCR service or app server. Only the reviewed text goes to the plate lookup. Video is not saved as a recording. Closing/hiding the scanner releases its camera tracks. Recognition can be wrong; check ambiguous characters and the plate/state yourself.

Install the PWA from its install control/browser menu. A phone needs a trusted HTTPS address for camera access and installation. Shell/OCR assets may be cached, but private data requires a live session check on a fresh launch; API responses are never cached and writes are not queued offline. An authenticated open page may remain visible during an interruption. Signing out clears the private UI and tab drafts, not the database.
