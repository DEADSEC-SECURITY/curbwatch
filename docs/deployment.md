# Deployment

## Service layout

One image supports `api`, `viewer`, `worker`, `scheduler` and `init` command arguments (or PARKING_ROLE). All long-running roles use the same persistent SQLite/data directory and queue. Use one scheduler. SQLite/WAL is intended for one host with local storage, not multi-node shared network filesystems. Horizontal API workers do not turn SQLite into a distributed database.

- **api** serves the authenticated app, private data APIs, settings and the public login shell.
- **viewer** serves only restricted read-only map APIs and a separate frontend. It has no owner routes or account management.
- **worker** performs serialized ticket checks and durable SMTP delivery tasks.
- **scheduler** queues checks/heartbeat/notification maintenance.
- **init** creates the schema, optional first admin and missing geometry cache, then exits.

Compose and the Terraform example create a fresh named volume. They do not automatically import a native installation's `data/`. To migrate, stop the native services, take a consistent SQLite backup and copy the data plus auth.key into the volume; ensure uid 10001 can read/write the directory. Preserve the existing database instead of starting from seed examples. No personal cars are seeded by current code.

## Containers

```sh
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m backend.manage create-admin --email you@example.com
```

The image runs as uid/gid 10001, keeps original/upstream license notices, and reads runtime env rather than baking deployment secrets into Vue or image layers. Compose publishes both HTTP services on loopback and keeps Redis off the host network. Configure real origins before proxying either app to other devices.

For read-only secret-file mounts, add an override such as:

```yaml
services:
  api:
    volumes:
      - /srv/curbwatch-secrets:/run/secrets:ro
  worker:
    volumes:
      - /srv/curbwatch-secrets:/run/secrets:ro
```

Mount files required by any other role there too if using a secret broker URL or external auth key. Set the corresponding `_FILE` options in `.env`; files must be readable by uid 10001. Compose merges distinct mount targets with the base data-volume mount. The Terraform example accepts a map of individual read-only host files and never reads their contents into configuration.

## Reverse proxy and HTTPS

Route the owner hostname to its API port and the public map hostname to its viewer port. Set PARKING_BASE_URL and PARKING_SHARE_BASE_URL to those exact external HTTPS origins, without paths. Register `${PARKING_BASE_URL}/api/auth/oidc/callback` as the provider's strict GET/query callback. Camera access and mobile PWA installation need trusted HTTPS. The application does not require public registration or expose private data through a shared-map bearer.

Use a proxy you control, matching the intended hostnames; do not blindly trust arbitrary forwarded headers. Configure trusted proxy addresses through Uvicorn's standard FORWARDED_ALLOW_IPS environment option when needed. Keep Redis private/authenticated as appropriate to the network. Filter callback query strings and credential headers from access logs; included app commands disable access logs. Same-origin frontend serving needs no CORS entry.

## Storage and recovery

Persist the SQLite database, auth.key (unless externally managed), geometry cache and scheduler state. Back up the database consistently using SQLite's backup API or after stopping services; do not copy a live WAL database with only its main file. Restore with compatible ownership. Do not synchronize open database files through cloud file-sync software.

Use `python -m backend.manage reset-admin --email ...` for local recovery. `--password-stdin` accepts a mounted deployment secret without a command-line password. Environment bootstrap only acts when the users table is empty. UI-managed OIDC/SMTP secrets need the same encryption key after restore; externally managed groups can instead use file/env secrets.

A failed first-start geometry download does not erase tickets. Retry `python -m backend.street_download`. Geometry updates use atomic replacement and the app refreshes its in-process cache when the file changes. Source data and map tiles retain their publisher's terms.

## Terraform

See [deploy/terraform](../deploy/terraform/README.md). The example builds this checkout and manages the single-host Docker services. It does not create DNS, a proxy or certificates, and no `terraform apply` is needed to validate it. For another Terraform platform, use the same role commands, environment map, secret mounts and persistent storage contract.
