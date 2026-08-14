# Development

Job Radar uses Python 3.14, `uv`, Docker Compose, and PostgreSQL 18.
SQLite is not part of the new application runtime.

## Local setup on Ubuntu

```bash
cp .env.example .env
uv sync
docker compose -f compose.yml up -d postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The PostgreSQL port is bound to localhost only. The API is also bound to localhost when run
through Compose, so OpenClaw on the same Ubuntu host can call it without traversing Cloudflare.

Run the complete stack with:

```bash
docker compose -f compose.yml up --build
```

Checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

`/health` is a liveness endpoint and does not depend on PostgreSQL. `/ready` returns HTTP 503 if
PostgreSQL is unavailable.

## Database schema

Alembic is the only schema authority. The application must not call `Base.metadata.create_all()`
at startup. Schema changes are introduced only through migrations.

## Secrets and local data

Never commit `.env`, CV files, database dumps, storage content, API keys, Telegram tokens, or raw
job payloads. Production secrets initially live in a mode-600 `.env` file on the VPS. A dedicated
secret manager remains a future hardening task.
