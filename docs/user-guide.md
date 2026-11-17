# User guide

## Garage and tickets

Add vehicles manually or scan a photo/live camera view. Review the exact plate, optional state, name and email. Every new plate must pass a successful ticket-source lookup before saving; zero matches require confirming the text. A no-ticket result is not registration validation. The Syracuse adapter searches by plate text, not state, and duplicate protection uses that text.

Initial tickets save atomically with the car. The reviewed lookup expires after ten minutes by default. Changing the plate or state invalidates it. Failures are never treated as empty results. Pausing a vehicle preserves its history; manually checking a paused vehicle is still possible.

Vehicle cards separate outstanding balance from total spent. “Total spent” sums recorded charges for tickets marked Paid in full; the source does not provide a complete transaction/partial-payment ledger. Ticket history includes paid/dismissed records and status/balance changes.

Import CSV or JSON from Ticket history. Use a License Plate column or select a vehicle. Imports are atomic; invalid rows roll back the file. Legacy timestamps remain unverified until a live lookup supplies a direct issue date, and imports do not overwrite more authoritative portal data.

## Street activity

On phones, the app opens on **Today** unless you follow a link to a specific screen. The bottom navigation opens Today, Map, Vehicles and Tickets. The header menu holds Settings, installation, importing, map sharing for administrators, and sign out. Ticket history uses cards on phones.

Today shows historical ticket activity for your current street and the current hour in the configured timezone, using the last 90 days independently of the map's exploration controls. Choose **Enable location** once; while permission remains granted, subsequent visits and returning to the foreground refresh your position automatically. Location needs HTTPS (or localhost for development). GPS coordinates remain in memory on your device and are not sent to the app server or saved in browser storage. Only the automatic-location preference is saved.

Location matching uses all covered streets, including those without ticket history. GPS accuracy worse than 60 metres requires manual selection; no match within 75 metres is treated as outside nearby coverage. At intersections or other ambiguous matches, choose a street. You can always choose a covered street manually, including when location permission is denied or unavailable. Manual selection is kept while the Today screen stays open. Coverage follows the deployment's Syracuse street geometry.

The summary shows Low, Moderate or High historical activity only when the existing sample requirements are met. Otherwise it shows Limited data or Not enough data, never a zero-risk prediction. Expand the evidence to see the ticket counts, whole-street precision and model limitations. This is not a calibrated probability of receiving a ticket. Returning to the app refreshes the result; interrupted connections label previously loaded activity as saved.

The default is the current configured timezone/hour and the last 90 days. Use “Base highlights on” in the map toolbar to choose 7/30/90/180/365 days or All history. The map always uses all monitored vehicles; the vehicle filter in Ticket history only filters that list. The selected date is the inclusive end of the window; future days are excluded. Counts in the timeline and map use the same period, exact hour and equal ticket weights. Changing the history window never deletes tickets.

The activity index is the fraction of a street's ticketed dates with at least one ticket in the selected hour. Low is below 25%, moderate below 60%, high at least 60%. A color score needs three exact-hour tickets across two dates. Sparse samples are blue dashed; gray means no exact-hour sample in the selected period. We do not know where cars were parked on days without tickets, so this is not a calibrated probability of officer presence.

Play loops 24 hour blocks at one- or two-second intervals and waits for each result. Manual period/date changes, dialogs, hidden tabs and navigation pause playback. Selection stays on the same street while hours change. Desktop map layouts fit the available window; long street lists/details scroll inside their panel. Phones use a large hour slider, with speed settings behind Playback options. Street details open in a bottom sheet that closes with its close button, Escape or a tap outside; keyboard focus stays inside the sheet while it is open. Shared maps use the same phone controls.

Locations identify streets, often multiple blocks; they do not identify exact patrol locations. Unmatched places are listed without invented coordinates. Background maps and the ticket portal need internet; downloaded road geometry is cached locally.

## Emails, accounts and sharing

A vehicle's optional email receives its new-ticket alerts and monthly outstanding summary after SMTP is enabled. Reports group that person's cars, including paused vehicles, and include every positive balance regardless of issue month. See [email behavior](email.md) for schedule, catch-up and retry details. Initial/imported history does not generate a batch of alerts.

Admins add/invite users in Settings. There is no public signup or automatic SSO enrollment. Users share the garage; admins also manage access, SMTP, OIDC and share links. Invitations are copied for private delivery rather than emailed automatically.

Share map creates an expiring, revocable link to the map/timeline only. Plates, emails, tickets, balances and all management controls remain private. Full link secrets appear only at creation and cannot be retrieved later. Keep and distribute the copied link appropriately.

## Camera, PWA and offline use

OCR runs locally with bundled Tesseract workers/models. No photos or videos go to a cloud OCR service or app server. Only the reviewed text goes to the plate lookup. Video is not saved as a recording. Closing/hiding the scanner releases its camera tracks. Recognition can be wrong; check ambiguous characters and the plate/state yourself.

Install the PWA from its install control/browser menu. A phone needs a trusted HTTPS address for camera access and installation. Shell/OCR assets may be cached, but private data requires a live session check on a fresh launch; API responses are never cached and writes are not queued offline. An authenticated open page may remain visible during an interruption. Signing out clears the private UI and tab drafts, not the database.
