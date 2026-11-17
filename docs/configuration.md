# Environment configuration

Process environment wins over an optional `.env` file. Native services load the project-root file automatically; set `PARKING_ENV_FILE` for another path. Compose reads its `.env` and forwards it to the app services. Terraform can inject environment directly, without creating a `.env`.

All options have safe defaults; a fresh database contains no cars or default user. Group-specific OIDC/SMTP environment options override the corresponding saved UI settings and make that group read-only in Settings. Leave the group unset to manage it through the UI. Never put real secrets in Git, image build arguments, browser config, or Terraform's ordinary environment map.

## Core services and storage

| Variable | Default | Meaning |
|---|---|---|
| `PARKING_ENV_FILE` | project `.env` | Optional configuration file; process environment has precedence |
| `PARKING_DATA_DIR` | project `data/` | Persistent SQLite, cache, encryption key and scheduler state; `/data` in containers |
| `PARKING_DATABASE_PATH` | `PARKING_DATA_DIR/parking.sqlite3` | SQLite file; place on persistent local storage |
| `PARKING_HOST` / `PARKING_SHARE_HOST` | `127.0.0.1` | Native owner/viewer listeners; image/Compose use container `0.0.0.0` |
| `PARKING_PORT` / `PARKING_SHARE_PORT` | 8000 /8002 | Owner/viewer listener ports |
| `PARKING_LISTEN_ADDRESS` | `127.0.0.1` | Compose host interface for published ports |
| `PARKING_BASE_URL` | `http://127.0.0.1:8000` | Exact external owner origin for OIDC callbacks, invitations and origin checks |
| `PARKING_SHARE_BASE_URL` | `http://127.0.0.1:8002` | External origin embedded in new restricted links |
| `PARKING_ROLE` | `api` | Image role when no command argument is supplied: api/viewer/worker/scheduler/init |
| `CELERY_BROKER_URL` | native `redis://127.0.0.1:6381/0` | Queue connection; Compose defaults to `redis://redis:6379/0` |
| `CELERY_BROKER_URL_FILE` | unset | Secret-file alternative, e.g. a credential-bearing Redis URL |
| `PARKING_TASK_QUEUE` | `parking_checker` | Use the same queue on API, worker and scheduler |
| `PARKING_TIMEZONE` | `America/New_York` | Valid IANA timezone for display, schedules, activity windows and ticket age |
| `PARKING_TIMEZONE_LABEL` | `Eastern time` for the default zone | Human-readable frontend/email label; another zone defaults to its IANA name |
| `PARKING_CORS_ORIGINS` | local Vite origins for HTTP; empty for HTTPS | Comma-separated separate frontend origins; same-origin deployments need none |

`CURBWATCH_IMAGE` and `REDIS_IMAGE` optionally change the Compose image names. Container listeners and host-published interfaces are distinct. External HTTPS origins must match the reverse proxy hostname; no path-prefix hosting is supported. Reverse-proxy access logs should omit OIDC callback query strings and all credentials.

## Collection, map and source

| Variable | Default | Meaning |
|---|---|---|
| `PARKING_CHECK_INTERVAL_SECONDS` | 3600 | Hourly default runs at minute 0; other values use a periodic interval (30–604800) |
| `PARKING_COLLECTOR_DELAY_SECONDS` | 1.1 | Delay between vehicle lookups (0–60); respect the upstream service |
| `PARKING_PORTAL_URL` | `https://mvb.syr.gov` | Base URL for the included Syracuse-compatible adapter; not a generic municipal adapter switch |
| `PARKING_PORTAL_TIMEOUT_SECONDS` | 25 | Per-request timeout (1–120) |
| `PARKING_PORTAL_RETRIES` | 3 | Source HTTP attempts (1–10) |
| `PARKING_PAYMENT_URL` | `https://mvb.syr.gov/` | Email payment button target; never submits a payment |
| `PARKING_LOOKUP_TTL_SECONDS` | 600 | Reviewed-plate lookup lifetime (60–3600) |
| `PARKING_DEFAULT_HISTORY_DAYS` | 90 | Default map period: 7/30/90/180/365, or 0 for all history |
| `PARKING_FETCH_STREETS_ON_START` | true | API/init role and native launcher download a missing geometry cache |
| `PARKING_STREETS_FILE` | `PARKING_DATA_DIR/streets.geojson` | Local runtime geometry; not included in source |
| `PARKING_STREETS_SOURCE_URL` | Syracuse ArcGIS road-inventory layer | ArcGIS FeatureServer layer URL for the downloader's expected fields |
| `PARKING_STREETS_ATTRIBUTION` | `City of Syracuse` | Attribution displayed with street lines |
| `PARKING_LOCATION_LABEL` | `Syracuse, New York` | Location shown in the map/workspace |
| `PARKING_MAP_STYLE_URL` | OpenFreeMap positron style | Browser-accessible MapLibre style JSON URL |
| `PARKING_MAP_LATITUDE` / `PARKING_MAP_LONGITUDE` | 43.039 /-76.135 | Initial map center |
| `PARKING_MAP_ZOOM` | 13.5 | Initial zoom (1–19) |

The city-source URL in `.env.example` is the complete default. Other geometry can be supplied in the app's GeoJSON schema; changing map settings does not add support for another ticket provider. `/runtime-config.js` exposes an explicit allowlist of public map/time settings, so Vue does not need a rebuild for deployment changes. No server environment dump or secret is exposed. Service workers never cache that script or API data.

## Accounts and SSO

| Variable | Default / meaning |
|---|---|
| `PARKING_SESSION_HOURS` | 8; absolute session lifetime (1–168) |
| `PARKING_INVITE_TTL_HOURS` | 168; one-use invitation lifetime (1–720) |
| `PARKING_COOKIE_SECURE` | Automatic with HTTPS; can force true but cannot disable it on an HTTPS origin |
| `PARKING_BOOTSTRAP_ADMIN_EMAIL` | First administrator email; used only on an empty users table |
| `PARKING_BOOTSTRAP_ADMIN_PASSWORD_FILE` / `PARKING_BOOTSTRAP_ADMIN_PASSWORD` | Initial password file preferred; minimum 12 characters; remove after bootstrap |
| `PARKING_AUTH_KEY_FILE` | `PARKING_DATA_DIR/auth.key`; generated with mode 0600 if absent; can be an existing read-only mounted Fernet key |
| `PARKING_AUTH_KEY` | Optional externally managed Fernet key instead of a key file |
| `PARKING_OIDC_ENABLED` | Defaults true when an environment issuer is set, otherwise false |
| `PARKING_OIDC_NAME` | Login button label; default Single sign-on |
| `PARKING_OIDC_ISSUER` | Exact issuer from provider discovery, including trailing slash |
| `PARKING_OIDC_DISCOVERY_URL` | Defaults issuer +`/.well-known/openid-configuration` |
| `PARKING_OIDC_CLIENT_ID` | Registered client ID |
| `PARKING_OIDC_CLIENT_SECRET_FILE` / `PARKING_OIDC_CLIENT_SECRET` | Client secret; file wins |
| `PARKING_OIDC_AUTH_METHOD` | client_secret_basic /client_secret_post /none |

Explicit OIDC settings make the provider environment-managed, including an explicit disable. There is no signup/JIT creation. See [authentication.md](authentication.md) for verified-email linking, Authentik issuer modes, first-admin CLI and recovery.

## SMTP and reporting

| Variable | Default / meaning |
|---|---|
| `PARKING_SMTP_HOST` | Server hostname/IP; not a URL |
| `PARKING_SMTP_PORT` | 587 |
| `PARKING_SMTP_SECURITY` | starttls /tls /loopback-only none |
| `PARKING_SMTP_USERNAME` | Optional for trusted relays |
| `PARKING_SMTP_PASSWORD_FILE` / `PARKING_SMTP_PASSWORD` | Password; file wins |
| `PARKING_SMTP_FROM_EMAIL` | Required sender when enabled |
| `PARKING_SMTP_FROM_NAME` | Curbwatch |
| `PARKING_SMTP_REPLY_TO` | Optional reply address |
| `PARKING_EMAIL_ENABLED` | false; explicit master switch |
| `PARKING_EMAIL_TICKET_ALERTS` | true |
| `PARKING_EMAIL_MONTHLY_REPORTS` | true |
| `PARKING_EMAIL_REPORT_DAY` | 1 (1–28) |
| `PARKING_EMAIL_REPORT_HOUR` / `PARKING_EMAIL_REPORT_MINUTE` | 9 /15 in the configured timezone |
| `PARKING_SMTP_TIMEOUT_SECONDS` | 10 (1–120) |
| `PARKING_EMAIL_INTERVAL_SECONDS` | 60; outbox/report maintenance interval (10–3600) |
| `PARKING_EMAIL_BATCH_SIZE` | 5; messages per delivery task (1–100) |
| `PARKING_EMAIL_MAX_ATTEMPTS` | 5; bounded automatic retry attempts (1–20) |

Explicit SMTP connection/policy/report settings make that group environment-managed. Engine timeout/batch/interval settings alone do not disable UI-managed SMTP. Supply the same settings and file mounts on API and worker. Standard OS CA configuration controls TLS trust; certificate verification cannot be turned off. See [email.md](email.md) for recipients, catch-up, deduplication and uncertain handoffs.
