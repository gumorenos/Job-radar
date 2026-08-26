# Job Radar

Job Radar is the main repository for a personal job-search operating system: sources discover opportunities, while Job Radar normalizes, deduplicates, applies business rules, explains fit, and supports the user's decisions and application workflow.

`main` is the current source of truth for this repository. Feature work is developed through short-lived branches and pull requests; there is no permanent "current development branch".

## Current personal v1 capabilities

- FastAPI + PostgreSQL ingestion API with Bearer authentication and idempotency.
- Durable worker queue for normalization, matching, notification delivery, and retries.
- Job/posting normalization, sightings, exact dedupe, uncertain duplicate review, and 30-day reappearance handling.
- Explainable `rules-v5` matching with hard business rules, positive HR/People fit, structured experience/degree/skills facts, transferable skills, salary assessment, career-move assessment, and approved CV recommendation.
- Human classification feedback that preserves the original system analysis, plus aggregated correction insights without automatically mutating rules.
- Radar UI with High Priority / Review / Discard / Possible Duplicates, structured decision brief, sources, and feedback.
- Applications CRM with independent lifecycle stages and notes.
- Versioned CV library with immutable file storage; AI-generated versions remain DRAFT until explicit approval.
- Editable candidate profile and an explicit `Reanalizar oportunidades` action for applying saved profile changes to active jobs.
- Dashboard notification center plus optional Telegram immediate/daily-review delivery with durable retries.
- Provider-neutral inbound-email foundation.
- Production-oriented Docker Compose, Alembic migrations, ARM64-compatible image build, deployment/preflight/backup/smoke scripts, and an isolated OpenClaw bridge.

## Runtime

- Python 3.14
- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL 18
- Docker Compose
- `uv` for Python dependency management
- ARM64-compatible deployment target on Oracle Cloud Ubuntu

## Validation

The GitHub Actions quality gate runs Ruff, mypy, frontend JavaScript syntax checks, deployment script syntax checks, production Compose validation, Docker image build, unit tests, Alembic upgrade, and PostgreSQL integration tests.

Real Oracle ARM64 deployment, browser QA, Cloudflare routing/Access, and live OpenClaw integration are separate operational gates.

## Production status

A prior Job Radar core release is already running on the Oracle ARM64 VPS in **localhost-only** mode. The last confirmed deployed baseline is `7659e77d38a2a61ecc352b49d2481d86d788a5e5`, with API on `127.0.0.1:8010`, PostgreSQL on `127.0.0.1:5432`, and the worker without a host port.

The isolated OpenClaw bridge has passed staged installation and canary QA and is enabled, while the existing Notion/Supabase/Fast.io path remains in parallel. Real dual-write burn-in still requires a naturally arriving vacancy batch. There is no public Job Radar hostname or Cloudflare Access gate yet, and production Telegram delivery remains disabled/unconfirmed.

Repository `main` is newer than the deployed core and must be upgraded through an immutable image, verified pre-upgrade backup, preflight, migrations, smoke, data validation, and canary. PostgreSQL must never be exposed publicly; Cloudflare Access/app authentication remains a prerequisite before public web exposure.

See `docs/development.md`, `docs/core-completion.md`, `docs/production-status.md`, `docs/deployment.md`, `docs/release-upgrade-checklist.md`, and `docs/qa-pending.md` for development, product scope, operational truth, deployment, upgrade, and remaining QA details.

## Historical scripts and the original MVP

Scripts retained in this repository remain useful references where applicable. The separate original MVP repository continues independently; this repository does not redefine or deprecate it.
