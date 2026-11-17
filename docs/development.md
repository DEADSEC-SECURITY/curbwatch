# Development

Python 3.12+ and Node.js 26 are required; Linux/Python 3.14 is the tested baseline. Native launch uses Docker for a dedicated local Redis container. You can also supply CELERY_BROKER_URL for another broker.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m pytest -q
npm test --prefix frontend
.venv/bin/ruff check backend scripts tests
.venv/bin/ruff format --check backend scripts tests
npm run format:check --prefix frontend
```

Backend tests use isolated databases, synthetic plates and synthetic geometry. Portal HTTP tests start the included non-forwarding Node simulation automatically. SMTP tests use local capture servers with a test CA for real STARTTLS/SMTPS handshakes; no owners are emailed. Live identity-provider/deliverability checks remain deployment-specific. Do not run tests against your production database.

For the complete native service group, run `./start.sh`. It reads `.env`, installs locked runtime packages, builds Vue and starts both APIs, worker and scheduler. Ctrl+C or `python scripts/stop_local.py` stops that group's processes without deleting data. Vite hot reload: keep the API running, then `npm run dev --prefix frontend`; port 5173 proxies APIs and runtime config to the local services.

## Layout

| Path | Purpose |
|---|---|
| `backend/main.py`, `shared.py` | Separate private and restricted-viewer ASGI boundaries |
| `backend/auth.py`, `oidc.py`, `manage.py` | Accounts, invitations, OIDC and local recovery |
| `backend/collector.py`, `portal.py`, `plate_validation.py` | Serialized collection and reviewed plate lookup |
| `backend/notifications.py`, `mail_config.py`, `email_templates.py` | Durable outbox, SMTP configuration/delivery and email design |
| `backend/activity.py`, `streets.py`, `street_download.py` | Unweighted selected-period summaries and geometry cache |
| `backend/config.py`, `runtime.py`, `entrypoint.py` | Validated env settings, public allowlist and service roles |
| `frontend/src/components/`, `scanner/`, `timeline/` | Reusable UI, on-device OCR and playback |
| `tests/`, `frontend/tests/` | Behavioral API/SMTP/HTTP/OCR/lifecycle tests |
| `docs/api/` | Exported OpenAPI and behavioral contracts |
| `postman/` | Synthetic portal simulation |
| `deploy/terraform/` | Docker Terraform deployment example |
| `scripts/` | Native launch/stop, schema export and geometry download wrappers |
| `data/`, `artifacts/` | Ignored local records/previews; never publish these |

Regenerate contracts with `python scripts/export_openapi.py`. Keep `.env.example` and configuration docs updated when introducing settings. Runtime/frontend config must remain an allowlist with no secrets. Preserve per-ticket/outbox atomicity and restricted-viewer redaction when changing backend behavior.

Frontend preparation generates icons, OCR assets, plate-state JSON and third-party license copies. These files are not committed. Production dependency pins live in requirements.lock.txt; development-only tools are separate in requirements-dev.lock.txt. The frontend lockfile is committed; use npm ci.

## Local geometry

The real road dataset is downloaded into runtime storage and is not licensed as project source. Tests deliberately use a small generated fixture. Default downloader expects the Syracuse ArcGIS schema; supporting another municipality requires an adapter for that provider/schema, not just changing a URL.
