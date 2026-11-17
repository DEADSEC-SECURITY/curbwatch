# Local map sharing contract

The private owner app stays on loopback port 8000. A separate ASGI app on loopback
port 8002 serves only the shared map. The owner service requires account login;
share management requires an administrator. The viewer remains account-free.
Future hosting requires explicit origin/HTTPS configuration; see docs/authentication.md.

## Owner service

- `GET /api/shares`: list links (id, label, creation/expiry/revocation timestamps,
  status), plus configured share base URL and local-only notice. Never return
  stored token hashes or existing bearer tokens.
- `POST /api/shares`: `{name: string <= 80, expires_in_days: 7 | 30 | null}`;
  default label "Map link", default expiry 30 days. Return 201 with link metadata
  and its full URL once. Tokens have 256 bits of random entropy and only their
  SHA-256 hashes are persisted. The URL carries the token in its fragment.
- `POST /api/shares/{id}/revoke`: mark revoked, idempotently; unknown id -> 404.

These management routes exist only on the owner service and retain the existing
same-origin write protection, an active administrator session and CSRF token. No share bearer grants access to owner routes.

## Shared service

- `GET /share/`: standalone shared frontend, without owner navigation, storage
  snapshots, PWA worker, install UI, camera, car filter, or ticket history.
- `GET /api/shared/activity?day=YYYY-MM-DD&hour=0..23&history_days=90`: requires
  `Authorization: Bearer <token>` on every request. Defaults to current Eastern
  date/hour and 90 days of history. Select 7,30,90,180,365 or 0 (all history). Only allowlisted aggregated street summaries, geometry, scores,
  model settings and hourly totals. No plates, names, contacts, car ids,
  ticket ids/numbers, money, raw payloads, individual issue times or check errors.
- `GET /api/shared/streets`: same authorization; street geometry only.
- Missing, malformed, unknown, expired or revoked token -> identical 404.
- `car_id` filtering -> 400. Invalid date/hour -> 422 after authorization.
- Owner routes, docs, schema and writes -> 404/405 on this service, including
  when a valid share token is provided. Static assets never fall back to the
  owner app or API. API data uses `Cache-Control: no-store`; shared pages set
  `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex, nofollow` and deny framing.
- No caching of shared map data in localStorage, a service worker, or cookies.
  The viewer revalidates on timeline changes and every minute, clearing displayed
  results when authorization fails.

Local automated tests use synthetic data and separate owner/viewer clients to
verify redaction, write denial, expiration, revocation, tampering, filter denial,
and preservation of owner features. Browser checks cover creating/opening a
link, timeline interaction and revoking an open view. No public exposure is made.
