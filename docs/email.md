# SMTP ticket alerts and monthly reports

Email delivery is off until an administrator configures and enables it. No real SMTP account or recipient is configured automatically. Set each car's optional email under **Vehicles → Edit**. The car's contact receives its ticket notifications; account/login emails are independent. Cars with missing or invalid email addresses are skipped, and Settings shows how many need an address. Clearing a car's email stops future messages and cancels previously queued messages for that recipient at delivery time.

## Configure and check delivery

Open **Settings → Email notifications** as an administrator. Set host, port, connection security, sender email/name, and credentials if required. STARTTLS (usually 587) and TLS from connection start (usually 465) both require certificate verification. Plain SMTP is permitted only for loopback capture/relay servers. There is no insecure-certificate override or automatic plaintext fallback.

Select new-ticket alerts and/or monthly summaries, choose the report schedule, then save and enable delivery. Blank password preserves a stored secret; the remove-password checkbox clears it for a trusted unauthenticated relay. Stored passwords use the same deployment encryption key as SSO (`PARKING_AUTH_KEY` / `PARKING_AUTH_KEY_FILE`, default `data/auth.key`, mode 0600). Back up that key with the database. Passwords and raw server errors are never returned by the API or displayed in delivery status.

Use the two Preview links to inspect sample emails with synthetic plates/tickets. Enter a specific test recipient and click **Send test email**. This queues an actual SMTP test, containing no real ticket details. The Celery worker sends queued messages approximately once a minute while running; collection uses the same worker, so a long check can delay a notification. Recent deliveries shows queued, SMTP-accepted, failed and unconfirmed outcomes. SMTP acceptance does not prove inbox delivery; check spam/bounce handling at your mail provider. Configure SPF/DKIM/DMARC for the sender domain with that provider as part of deployment.

## Environment-managed SMTP

Any explicit SMTP connection or email policy setting makes email settings read-only in the UI. Engine timeout/batch settings alone do not. Environment-managed configuration overrides stored settings, without relying on their encryption key. Set the same SMTP and email policy environment values on **both API and worker**. Compose loads its optional `.env` on those services; native launchers read `.env` and inherit exported variables with higher precedence. Mount password files into every service that needs them. The scheduler does not send email itself.

| Variable | Default / purpose |
|---|---|
| `PARKING_SMTP_HOST` | Hostname or IP, without scheme/port. Omit for UI-managed configuration. |
| `PARKING_SMTP_PORT` | 587 |
| `PARKING_SMTP_SECURITY` | `starttls`, `tls`, or loopback-only `none` |
| `PARKING_SMTP_USERNAME` | Empty for an unauthenticated trusted relay |
| `PARKING_SMTP_PASSWORD_FILE` | Mounted secret file, preferred over `PARKING_SMTP_PASSWORD` |
| `PARKING_SMTP_FROM_EMAIL` | Required when enabled; a sender your SMTP service permits |
| `PARKING_SMTP_FROM_NAME` | Curbwatch |
| `PARKING_SMTP_REPLY_TO` | Optional reply address |
| `PARKING_EMAIL_ENABLED` | false; explicit master delivery switch |
| `PARKING_EMAIL_TICKET_ALERTS` | true |
| `PARKING_EMAIL_MONTHLY_REPORTS` | true |
| `PARKING_EMAIL_REPORT_DAY` | 1 (allowed 1–28) |
| `PARKING_EMAIL_REPORT_HOUR` | 9, America/New_York |
| `PARKING_EMAIL_REPORT_MINUTE` | 15 |

See `.env.example` for copyable variable names. Restart the native launcher/API/worker after environment changes. UI-managed changes are read before each delivery. Changing the master switch to off pauses queued messages. Disabling one notification type suppresses queued messages of that type when the worker next processes them. No historical ticket backlog is created by enabling email. Invitation links are still copied for private delivery; this feature does not email account invitations.

## New ticket behavior

A collector discovery (hourly or Check now) that inserts a previously unseen ticket also inserts one durable outbox event in the **same SQLite transaction**. Subsequent checks and balance/status changes do not create more alerts. New-ticket alerts start with future checks. A newly added vehicle's initial saved history and manual imports are not emailed as a historical batch. No email is queued while the master switch or ticket-alert switch is off. A valid car recipient is required at the time of discovery; later adding an email does not send old alerts retrospectively.

Each email contains the vehicle name/plate/state, ticket number, violation/location, verified issue date and age where available, current status, charges and current outstanding amount. The **Pay tickets** button opens exactly `https://mvb.syr.gov/`; it does not submit payment or claim that a ticket is paid.

## Monthly reports

Default: **the 1st at 09:15 Eastern**. A maintenance task checks eligibility each minute and generates at most one batch per calendar month. If the app was stopped at the scheduled time, the current month's batch catches up on resume. Enabling monthly delivery after that time generates the current month's report once. Older months are not backfilled, and obsolete queued monthly reports are cancelled rather than delivered in a later month. Moving the schedule after a batch has already run does not produce a second batch that month.

Recipients are normalized and grouped across all their vehicles, including paused vehicles. Each report includes **all current positive ticket balances**, regardless of issue month, the total balance, and each ticket's own amount and elapsed calendar days since issue in America/New_York. No outstanding tickets means no report; an empty monthly batch still counts as that month's run. New recipients added after a completed batch start receiving monthly reports with the next batch.

Balances and recipients are checked again at delivery time. If tickets were paid while queued, they are removed; if nothing remains, the report is cancelled. Unverified, unavailable or implausible issue dates are labeled rather than turned into invented ages. Collection/payment timestamps are never substituted for the issue date. All balances come from the latest successful portal check; the email asks the owner to confirm the final amount at the city portal.

## Delivery reliability and recovery

SQLite stores the outbox and monthly batch markers. Unique ticket/month-recipient keys suppress routine duplicates, and messages retain their Message-ID across retries. The worker claims each message with a bounded lease and never sends while holding a database transaction. Safe transient failures use bounded backoff (up to five attempts); explicit permanent SMTP rejections stop and appear in Settings. Delivery failures do not roll back ticket collection.

SMTP cannot guarantee exactly-once delivery if a connection/process fails after handing off a message but before recording acceptance. These outcomes become **Unconfirmed**, without an automatic resend. Expired sending leases are treated the same way. Check the recipient's mailbox; the UI requires acknowledging a possible duplicate before retrying an unconfirmed message. A failed message can also be retried after fixing configuration. Retries recheck recipient, policy and current balances. No debug-level SMTP logging is enabled, so credentials and message bodies are not written to logs.

## Validation and artifacts

`tests/test_email.py` uses isolated SQLite databases, synthetic addresses and a local SMTP capture server. It exercises MIME HTML/text, exact payment link, recipient isolation, age/totals, collector deduplication, month boundaries/catch-up, paid/missing-address suppression, retry/ambiguous handoff, admin/CSRF protection, encrypted password redaction and real STARTTLS/SMTPS handshakes with a test CA. No real owners are emailed by those tests. Live provider deliverability remains a deployment check.

API contract: `docs/api/email-contract.md` and `docs/api/openapi.json`. The public shared-map service has no email endpoints.
