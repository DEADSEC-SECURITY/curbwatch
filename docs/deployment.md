# Deployment

## Service layout

One image supports `api`, `viewer`, `worker`, `scheduler` and `init` command arguments (or PARKING_ROLE). All long-running roles use the same persistent SQLite/data directory and queue. Use one scheduler. SQLite/WAL is intended for one host with local storage, not multi-node shared network filesystems. Horizontal API workers do not turn SQLite into a distributed database.

- **api** serves the authenticated app, private data APIs, settings and the public login shell.
- **viewer** serves only restricted read-only map APIs and a separate frontend. It has no owner routes or account management.
- **worker** performs serialized ticket checks and durable SMTP delivery tasks.
- **scheduler** queues checks/heartbeat/notification maintenance.
- **init** creates the schema, optional first admin and missing geometry cache, then exits.

Compose and the Terraform example create a fresh named volume. They do not automatically import a native installation's `data/`. To migrate, stop the native services, take a consistent SQLite backup and copy the data plus auth.key into the volume; ensure uid 10001 can read/write the directory. Preserve the existing database instead of starting from seed examples. No personal cars are seeded by current code.

## Deploy the published image

The Docker Hub image is `elgon2003/curbwatch`, currently for `linux/amd64`. It includes the built frontend, bundled OCR assets, all service roles, license notices and deployment templates. There are no default accounts or personal records in the image.

Create an empty deployment directory, then extract the standalone Compose file from the image:

```sh
docker run --rm --entrypoint cat elgon2003/curbwatch:latest /app/.deploy/compose.yaml > compose.yaml
docker compose up -d
docker compose exec api python -m backend.manage create-admin --email you@example.com
```

Open `http://127.0.0.1:8000`. Shared map links use port 8002. This starts Redis, the owner app, the restricted map service, one worker and one scheduler. All app roles share a named data volume. The deployment only needs its Compose file and an optional `.env`; it never builds from source.

For custom settings, extract the included public template and edit `.env` before startup:

```sh
docker run --rm --entrypoint cat elgon2003/curbwatch:latest /app/.deploy/env.example > .env
```

For example, set `CURBWATCH_IMAGE=elgon2003/curbwatch:0.2.0` to pin a release, or configure external HTTPS origins. Do not overwrite an existing `.env` when updating. To update containers while retaining their volume:

```sh
docker compose pull
docker compose up -d
```

The repository's [compose.hub.yaml](../compose.hub.yaml) is the same standalone deployment file. When using that filename directly, add `-f compose.hub.yaml` to Compose commands. Both variants use the `curbwatch` project name and the same named volume as the source-build Compose file when run on the same Docker host. Changing deployment directories does not create a separate garage unless you also choose a different project name with `-p`.

## Build from source

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

## Publish to Docker Hub

For a manual publish, authenticate with `docker login` and build from a reviewed checkout. Use a new version tag for each release; update `latest` to the same tested image:

```sh
docker build --build-arg VERSION=0.2.0 --build-arg VCS_REF="$(git rev-parse HEAD)" -t elgon2003/curbwatch:0.2.0 .
docker run --rm -e PARKING_FETCH_STREETS_ON_START=false elgon2003/curbwatch:0.2.0 init
docker tag elgon2003/curbwatch:0.2.0 elgon2003/curbwatch:latest
docker push elgon2003/curbwatch:0.2.0
docker push elgon2003/curbwatch:latest
```

The [Publish Docker image workflow](../.github/workflows/publish-image.yml) runs the existing CI checks before publishing. Add a Docker Hub personal access token for `elgon2003` with write access as the GitHub Actions repository secret `DOCKERHUB_TOKEN`. Never commit the token. Run the workflow manually with a tag, or publish a GitHub release: `v0.2.0` publishes `0.2.0`, and a stable release also updates `latest`. Prereleases do not update `latest`. The workflow builds Linux amd64 images, includes SBOM/provenance attestations, and pins its actions to reviewed revisions.

## Reverse proxy and HTTPS

Route the owner hostname to its API port and the public map hostname to its viewer port. Set PARKING_BASE_URL and PARKING_SHARE_BASE_URL to those exact external HTTPS origins, without paths. Register `${PARKING_BASE_URL}/api/auth/oidc/callback` as the provider's strict GET/query callback. Camera access and mobile PWA installation need trusted HTTPS. The application does not require public registration or expose private data through a shared-map bearer.

Use a proxy you control, matching the intended hostnames; do not blindly trust arbitrary forwarded headers. Configure trusted proxy addresses through Uvicorn's standard FORWARDED_ALLOW_IPS environment option when needed. Keep Redis private/authenticated as appropriate to the network. Filter callback query strings and credential headers from access logs; included app commands disable access logs. Same-origin frontend serving needs no CORS entry.

## Storage and recovery

Persist the SQLite database, auth.key (unless externally managed), geometry cache and scheduler state. Back up the database consistently using SQLite's backup API or after stopping services; do not copy a live WAL database with only its main file. Restore with compatible ownership. Do not synchronize open database files through cloud file-sync software.

Use `python -m backend.manage reset-admin --email ...` for local recovery. `--password-stdin` accepts a mounted deployment secret without a command-line password. Environment bootstrap only acts when the users table is empty. UI-managed OIDC/SMTP secrets need the same encryption key after restore; externally managed groups can instead use file/env secrets.

A failed first-start geometry download does not erase tickets. Retry `python -m backend.street_download`. Geometry updates use atomic replacement and the app refreshes its in-process cache when the file changes. Source data and map tiles retain their publisher's terms.

## Terraform

See [deploy/terraform](../deploy/terraform/README.md). The example builds this checkout and manages the single-host Docker services. It does not create DNS, a proxy or certificates, and no `terraform apply` is needed to validate it. For another Terraform platform, use the same role commands, environment map, secret mounts and persistent storage contract.
