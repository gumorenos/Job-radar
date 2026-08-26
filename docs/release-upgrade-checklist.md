# Job Radar — controlled localhost upgrade checklist

Use this checklist for upgrading an already-running localhost-only Job Radar installation to a newer immutable `main` image.

## Before touching runtime

- Record the currently deployed application image and repository SHA.
- Record the target `main` SHA and confirm the matching ARM64 `sha-<commit>` GHCR image exists.
- Confirm `/srv/job-radar/app` is clean and `.env.production` remains mode `0600`.
- Record API/PostgreSQL bindings and the health of unrelated VPS services.
- Do not modify Cloudflare, the loan-calculator tunnel, OpenClaw gateway, or unrelated containers.

## Required backup gate

Before changing `JOB_RADAR_IMAGE` or running migrations:

```bash
bash ops/backup.sh .env.production /srv/job-radar/backups 14
```

Proceed only when the command reports both `BACKUP_VERIFY_OK` and `BACKUP_OK`. Record the dump and checksum paths. The verification must include a full disposable restore drill.

## Upgrade

1. Change only `JOB_RADAR_IMAGE` in `.env.production` to the immutable target `sha-<commit>` tag.
2. Run `bash ops/preflight.sh .env.production`.
3. Run `bash ops/deploy.sh .env.production`.
4. Run `bash ops/smoke.sh .env.production`.
5. Confirm Alembic is at `head`, API/PostgreSQL remain loopback-only, and worker is running.
6. Confirm existing Job Radar data remains present.
7. Confirm unrelated services are unchanged.

## Application canary

After the upgrade, send one controlled ingestion through the localhost API or the already-installed OpenClaw bridge. Confirm normalization, matching, Radar visibility, and idempotent retry without duplicate Job/Posting/Sighting/Analysis rows.

Do not remove the existing OpenClaw -> Notion path during this gate.

## Rollback boundary

Application rollback may repin the previous known-good image and rerun deploy/smoke. Do not downgrade Alembic automatically. If a migration introduces a data problem that cannot be handled forward, stop and use the verified pre-upgrade backup with an explicit restore plan.

## Public exposure

Cloudflare hostname/Access and Telegram are separate gates. A successful localhost upgrade does not authorize public exposure or notification enablement.
