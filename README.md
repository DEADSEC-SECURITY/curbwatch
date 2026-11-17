# Curbwatch

Self-hosted parking-ticket monitoring, a street activity map, and an installable phone-friendly app. FastAPI + Vue, SQLite, Celery and Redis. The included ticket adapter supports Syracuse, New York.

**Source-available for noncommercial use.** Personal use and modification are permitted under [PolyForm Noncommercial 1.0.0](LICENSE). Commercial use requires separate permission; see [NOTICE](NOTICE). This is not an OSI open-source license. Third-party components retain their [own terms](THIRD_PARTY_NOTICES.md).

## What it does

- Track plates with optional name, state and contact email; check new plates before saving.
- Collect tickets on a configurable schedule, keeping history and payment/status changes.
- Explore exact-hour street activity using a week, month, three months, six months, year or all history. No age weighting. These are observations, not live patrol locations or calibrated probabilities.
- Scan a photo or live camera view with on-device OCR. Photos/video are not uploaded.
- Send an email for each new ticket and a monthly outstanding report with balances, ticket ages and a payment link.
- Sign in locally or with Authentik/another OIDC provider. No public signup; admins invite users.
- Share a restricted read-only map without exposing plates, emails, tickets or admin controls.

New installations start with an empty garage. No personal records or municipal road dataset are shipped in the repository.

## Start with Docker Compose

Requires Docker with Compose v2.24+.

```sh
git clone https://github.com/DEADSEC-SECURITY/curbwatch.git
cd curbwatch
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m backend.manage create-admin --email you@example.com
```

The admin command prompts for a password. Open [the owner app](http://127.0.0.1:8000). Shared links use port 8002. Published ports stay on loopback by default. First startup downloads street geometry into the persistent data volume; if unavailable, retry with `docker compose exec api python -m backend.street_download`.

For external access, configure the two public base URLs and a trusted HTTPS reverse proxy. Phone cameras and PWA installation need HTTPS. Do not expose Redis. Configure SMTP/OIDC in admin Settings or entirely through environment variables; secrets can be mounted as files.

## Deployment and configuration

- [Complete environment reference](docs/configuration.md) and [.env.example](.env.example)
- [Container/service roles, reverse proxy and storage](docs/deployment.md)
- [Terraform Docker example](deploy/terraform/README.md)
- [Login, Authentik/OIDC, invitations and recovery](docs/authentication.md)
- [SMTP setup, reports and delivery retries](docs/email.md)
- [User guide](docs/user-guide.md)
- [Development, testing and repository layout](docs/development.md)
- [API contracts](docs/api/README.md)

The same image runs `api`, `viewer`, `worker`, `scheduler` and one-shot `init` roles. Runtime frontend configuration is served separately, so changing origins, timezone, map settings or default history does not require rebuilding Vue. SQLite is intended for a single-host deployment with persistent local storage and one scheduler.

## Native development

Requires Python 3.12+, Node.js 26 and Docker for the local Redis service.

```sh
./start.sh
# First-admin setup in another terminal:
.venv/bin/python -m backend.manage create-admin --email you@example.com
```

The launcher reads `.env`, builds the frontend and starts both APIs, worker and scheduler. Your data stays in `data/`. Stop it with Ctrl+C or `.venv/bin/python scripts/stop_local.py`. See the development guide for hot reload and tests.

## Contributions and commercial licensing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue containing private plates, credentials or tickets. For commercial licensing, contact the [maintainer](https://github.com/DEADSEC-SECURITY).
