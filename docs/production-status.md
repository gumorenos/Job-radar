# Job Radar — current production status

Operational truth as last confirmed through OpenClaw QA:

- Job Radar is already running on the Oracle ARM64 VPS in **localhost-only** mode.
- Current deployed core image/repository baseline: `7659e77d38a2a61ecc352b49d2481d86d788a5e5`.
- API: `127.0.0.1:8010`.
- PostgreSQL: `127.0.0.1:5432`.
- Worker runs without a host port.
- The OpenClaw bridge has been installed, canary-tested, and enabled as a managed cron entry.
- The bridge canary passed idempotency and downstream normalization/matching checks.
- A real post-cutoff vacancy batch had not yet appeared during the observed burn-in window, so real dual-write burn-in remains unconfirmed.
- Existing OpenClaw -> Notion/Supabase/Fast.io behavior remains in place and must not be removed yet.
- No public Job Radar hostname or Cloudflare Access gate has been enabled for Job Radar.
- Telegram production delivery remains disabled/unconfirmed.

The repository `main` may be substantially newer than the deployed core image. Upgrades must therefore follow `docs/release-upgrade-checklist.md`: immutable target image, verified pre-upgrade backup with disposable restore drill, preflight, deploy, smoke, data validation, and canary.

This status document is operational context, not authorization to modify Cloudflare, unrelated services, the loan-calculator tunnel, or OpenClaw application code.
