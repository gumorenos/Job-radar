# Job Radar production deployment

This runbook deploys the personal v1 core to the Oracle ARM64 VPS without exposing PostgreSQL or the API directly to the internet.

## Production topology

```text
OpenClaw (host) -> 127.0.0.1:${JOB_RADAR_PORT} -> Job Radar API (Docker)
                                                        -> PostgreSQL (Docker)
                                                        -> worker (Docker)

Cloudflare systemd tunnel -> 127.0.0.1:${JOB_RADAR_PORT} -> dashboard/API
```

- API host binding: loopback only. Current selected production port: `127.0.0.1:8010` because `8000` is already owned by `oraculo-prod-api-1` on this VPS.
- PostgreSQL host binding: `127.0.0.1:5432`.
- Worker publishes no port.
- Existing unrelated Cloudflare/Docker services must not be modified.
- The existing host `cloudflared` systemd tunnel is the intended tunnel for Job Radar, but public exposure is a separate post-deploy step.
- Do not expose the dashboard publicly without Cloudflare Access or equivalent protection.

## Release image

`.github/workflows/publish.yml` publishes ARM64 images to GHCR after changes reach `main`:

- `ghcr.io/gumorenos/job-radar:main`
- `ghcr.io/gumorenos/job-radar:sha-<full-main-commit>`

Production must pin the immutable `sha-...` tag in `JOB_RADAR_IMAGE`; `main` is for inspection, not deployment pinning.

The Docker image contains the OCI source label so GHCR links it to this repository. Package visibility is a separate GitHub setting: if anonymous pull is denied, stop and report it. Either make the package public intentionally or provision an authorized registry credential; do not improvise/store a PAT without approval.

## First deploy preparation

On the VPS, use `/srv/job-radar` and create:

- `/srv/job-radar/app` — repository checkout
- `/srv/job-radar/storage` — application file storage
- `/srv/job-radar/backups` — local PostgreSQL dumps
- `/srv/job-radar/app/.env.production` — mode `0600`, never committed

Start from `.env.production.example`. Generate URL-safe secrets with `openssl rand -hex 32`. Replace the image tag with the exact validated `main` commit image.

Telegram stays disabled for the first deploy.

## Preflight

Before changing anything, record architecture/resources, Docker/Compose, listeners, existing containers/systemd services, current cloudflared state and unrelated-service health.

Then run:

```bash
bash ops/preflight.sh .env.production
```

The script fails before deployment if the selected API/PostgreSQL loopback ports are already owned by another service. It permits those ports when the corresponding Job Radar Compose service is already running during a later upgrade.

The current Oracle preflight established that `127.0.0.1:8000` is unavailable and `127.0.0.1:5432` is free. `8010` is the selected API candidate and must be rechecked immediately before first deploy.

Do not consolidate or modify unrelated Cloudflare tunnels/containers.

## Deploy

From `/srv/job-radar/app` at the exact target `main` commit:

```bash
bash ops/deploy.sh .env.production
bash ops/smoke.sh .env.production
```

`deploy.sh` runs the port preflight, validates production placeholders, pulls the pinned image, starts PostgreSQL, runs `alembic upgrade head`, starts API/worker and waits for `/ready`.

The first deployment stays localhost-only until runtime validation passes.

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

Only after localhost smoke and OpenClaw canary pass.

The existing main `cloudflared` service is token-run and currently has no local `/etc/cloudflared/config.yml`. Therefore do not assume hostname ingress can be edited on disk and do not rewrite/restart the service merely to expose Job Radar. Configure the hostname/route through the Cloudflare-managed tunnel control plane that owns that token, then point it to `http://127.0.0.1:${JOB_RADAR_PORT}` and protect it with Cloudflare Access before external use.

The current systemd warning that the cloudflared unit changed on disk is unrelated operational debt. Do not run `daemon-reload` or restart cloudflared as part of the Job Radar deployment unless separately approved and validated for all tunnel users.

The ingestion path for host-local OpenClaw remains localhost, not the public hostname.

## OpenClaw cutover

After deployment, follow `docs/openclaw-ingestion.md`.

Initial burn-in keeps the existing OpenClaw -> Notion path in parallel with OpenClaw -> Job Radar. Remove the Notion write only after real jobs are arriving, deduplicating, analyzing and appearing in Radar as expected.

## Definition of production-ready

- exact `main` commit and immutable image recorded;
- selected loopback API port documented and conflict-free;
- API/worker/PostgreSQL healthy on ARM64;
- Alembic at head;
- API/PostgreSQL loopback-only;
- verified local backup exists;
- dashboard protected before external exposure;
- OpenClaw canary ingestion succeeds without direct DB access;
- unrelated VPS services unchanged;
- rollback image recorded.
