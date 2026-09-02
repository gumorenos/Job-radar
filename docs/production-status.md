# Job Radar — current production status

Operational truth last confirmed through OpenClaw QA on 2026-09-02:

- Job Radar is running on the Oracle ARM64 VPS in **localhost-only** mode.
- Deployed repository/image target: `f831c7250820e8afd9c250cc69d5a98fa8cbb77c` / `ghcr.io/gumorenos/job-radar:sha-f831c7250820e8afd9c250cc69d5a98fa8cbb77c`.
- Alembic upgraded from `20260824_0006` to `20260901_0007 (head)`.
- API is healthy on `127.0.0.1:8010`.
- PostgreSQL is healthy on `127.0.0.1:5432`.
- Worker is running without a host port.
- Official smoke passed; `/health` and `/ready` returned HTTP 200. `/readiness` is not part of the official runbook and returned 404.
- Pre-upgrade PostgreSQL backup passed both checksum verification and a full disposable restore drill: `BACKUP_VERIFY_OK` + `BACKUP_OK`.
- Verified backup: `/srv/job-radar/backups/job-radar-20260902T042802Z.dump`, SHA-256 `2400b6929878b519265c5303d6b7c5af5347efadaa911799a44109bc466a0610`.
- Career Evidence Bank QA passed, including provenance, verification states, protected verified claims, archive/history, and validation behavior.
- Configurable Hard Rules QA passed. The three user toggles were restored to `true/true/true` after controlled canaries. Saving settings does not auto-reanalyze; explicit reanalysis queued the active set.
- Regression smoke passed for Radar, Applications, CVs, notifications, duplicates, ingestion, worker drain, and bridge idempotency.
- The managed OpenClaw bridge remains enabled. Existing OpenClaw -> Notion/Supabase/Fast.io behavior remains in parallel and **must not be removed yet**.
- Real post-cutoff dual-write burn-in remains unconfirmed: the latest QA used synthetic canaries and observed no new real vacancy during the validation window.
- Three synthetic QA postings remain in PostgreSQL because there is no deletion endpoint; treat them as test data, not real opportunities.
- No public Job Radar hostname or Cloudflare Access gate has been enabled for Job Radar.
- Telegram production delivery remains disabled/unconfirmed.
- Rollback reference image for the completed upgrade is `ghcr.io/gumorenos/job-radar:sha-fb694318cc0045ab4f20ad38c400d07febda8ecf`. Database migrations were not downgraded.

Future production upgrades must continue to follow `docs/release-upgrade-checklist.md`: immutable target image, verified pre-upgrade backup with disposable restore drill, preflight, deploy, smoke, data validation, and canary.

This status document is operational context, not authorization to modify Cloudflare, unrelated services, the loan-calculator tunnel, or OpenClaw application code.
