#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production env file: $ENV_FILE" >&2
  exit 1
fi

if ! grep -q '^JOB_RADAR_APP_ENV=production$' "$ENV_FILE"; then
  echo "JOB_RADAR_APP_ENV must be production." >&2
  exit 1
fi

if grep -Eq 'REPLACE_WITH|change-me|dev-only-change-me|job_radar_dev' "$ENV_FILE"; then
  echo "Production env still contains placeholder/development secrets." >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE")

"${compose[@]}" config >/dev/null
"${compose[@]}" pull postgres api worker
"${compose[@]}" up -d postgres

for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! "${compose[@]}" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
  echo "PostgreSQL did not become ready." >&2
  exit 1
fi

"${compose[@]}" run --rm --no-deps api alembic upgrade head
"${compose[@]}" up -d --no-build api worker

api_binding="$("${compose[@]}" port api 8000)"
api_port="${api_binding##*:}"
for _ in $(seq 1 30); do
  if curl --fail --silent --show-error "http://127.0.0.1:${api_port}/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/ready" >/dev/null

"${compose[@]}" ps

echo "Job Radar deployment healthy on ${api_binding}."
