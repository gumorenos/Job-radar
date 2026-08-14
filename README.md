# Job Radar

Job Radar is the main repository for the personal job-search intelligence system.

The current development direction is a modular FastAPI + PostgreSQL backend that centralizes job ingestion, normalization, deduplication, matching, classification, feedback, and notifications. Existing MVP scripts remain available while their useful logic is progressively migrated into the new application package.

## Current development branch

Active Phase 2 work is happening on `feat/phase-2-core-foundation`.

The older `feat/stage-1-api-foundation` branch is intentionally preserved as a reference and is not the target architecture.

## Runtime direction

- Python 3.14
- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL 18
- Docker Compose
- `uv` for Python dependency management
- ARM64-compatible deployment on Oracle Cloud Ubuntu

See `docs/development.md` for local development instructions.

## Legacy MVP

The existing scripts under `scripts/` are not being discarded. They contain useful scoring, normalization, candidate-profile, dashboard, and match-analysis logic that will be extracted into the new modular application in later phases.
