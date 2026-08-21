# Job Radar production deployment

This runbook deploys the personal v1 core to the Oracle ARM64 VPS without exposing PostgreSQL or the API directly to the internet.

## Production topology

```text
OpenClaw (host) -> 127.0.0.1:8000 -> Job Radar API (Docker)
                                      -> PostgreSQL (Docker)
                                      -> worker (Docker)

Cloudflare systemd tunnel -> 127.0.0.1:8000 -> dashboard/API
```

- API host binding: `127.0.0.1:8000`.
- PostgreSQL host binding: `127.0.0.1:5432`.
- Worker publishes no port.
- Existing unrelated Cloudflare/Docker services must not be modified.
- The existing host `cloudflared` systemd tunnel is the intended tunnel for Job Radar.
- Do not expose the dashboard publicly without Cloudflare Access or equivalent protection.

## Release image

`.github/workflows/publish.yml` publishes ARM64 images to GHCR after changes reach `main`:

- `ghcr.io/gumorenos/job-radar:main`
- `ghcr.io/gumorenos/job-radar:sha-<full-main-commit>`

Production must pin the immutable `sha-...` tag in `JOB_RADAR_IMAGE`; `main` is for inspection, not deployment pinning.

The Docker image contains the OCI source label so GHCR links it to this repository. Package visibility is a separate GitHub setting: if anonymous pull is denied, stop and report it. Either make the package public intentionally or provision an authorized registry credential; do not improvise/store a PAT without approval.

## First deploy preparation

On the VPS, use a dedicated directory such as `/srv/job-radar` and create:

- `/srv/job-radar/app` — repository checkout
- `/srv/job-radar/storage` — application file storage
- `/srv/job-radar/backups` — local PostgreSQL dumps
- `/srv/job-radar/app/.env.production` — mode `0600`, never committed

Start from `.env.production.example`. Generate URL-safe secrets with `openssl rand -hex 32`. Replace the image tag with the exact validated `main` commit image.

Telegram stays disabled for the first deploy.

## Preflight

Before changing anything, record:

- host architecture and free disk/RAM;
- Docker + Compose versions;
- listening ports;
- existing containers and systemd services;
- current `cloudflared` service/tunnel configuration;
- that ports 8000 and 5432 are available on loopback;
- that unrelated services are healthy.

Do not consolidate or modify unrelated Cloudflare tunnels/containers.

## Deploy

From `/srv/job-radar/app` at the exact target `main` commit:

```bash
bash ops/deploy.sh .env.production
bash ops/smoke.sh .env.production
```

`deploy.sh` validates production placeholders, pulls the pinned image, starts PostgreSQL, runs `alembic upgrade head`, starts API/worker and waits for `/ready`.

The first deployment should remain localhost-only until runtime validation passes.

## Backup

Create and validate a local custom-format PostgreSQL dump before upgrades and at least daily while the system contains useful data:

```bash
bash ops/backup.sh .env.production /srv/job-radar/backups 14
```

The script writes mode-0600 dumps, validates the archive with `pg_restore -l`, and removes dumps older than the retention period.

Local backup is not disaster recovery. External backup storage is still required before Job Radar becomes the sole copy of important job-search history.

## Rollback

Application rollback is image-based:

1. keep the previous known-good `sha-...` image tag;
2. set `JOB_RADAR_IMAGE` back to that tag;
3. run `bash ops/deploy.sh .env.production`;
4. run `bash ops/smoke.sh .env.production`.

Do not automatically downgrade database migrations. Before any future destructive migration, take a verified backup and define an explicit data rollback plan.

## Cloudflare exposure

Only after localhost smoke passes:

1. add a Job Radar hostname to the existing host `cloudflared` systemd tunnel pointing to `http://127.0.0.1:8000`;
2. protect the hostname with Cloudflare Access before treating it as a dashboard URL;
3. verify `/app/` through the hostname and confirm PostgreSQL remains unreachable externally.

The ingestion path for host-local OpenClaw remains `http://127.0.0.1:8000`, not the public hostname.

## OpenClaw cutover

After deployment, follow `docs/openclaw-ingestion.md`.

Initial burn-in keeps the existing OpenClaw -> Notion path in parallel with OpenClaw -> Job Radar. Remove the Notion write only after real jobs are arriving, deduplicating, analyzing and appearing in Radar as expected.

## Definition of production-ready

- exact `main` commit and immutable image recorded;
- API/worker/PostgreSQL healthy on ARM64;
- Alembic at head;
- API/PostgreSQL loopback-only;
- verified local backup exists;
- dashboard protected before external exposure;
- OpenClaw canary ingestion succeeds without direct DB access;
- unrelated VPS services unchanged;
- rollback image recorded.
