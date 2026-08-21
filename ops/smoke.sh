#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE")
api_binding="$("${compose[@]}" port api 8000)"
pg_binding="$("${compose[@]}" port postgres 5432)"

case "$api_binding" in
  127.0.0.1:*) ;;
  *) echo "API is not loopback-only: $api_binding" >&2; exit 1 ;;
esac

case "$pg_binding" in
  127.0.0.1:*) ;;
  *) echo "PostgreSQL is not loopback-only: $pg_binding" >&2; exit 1 ;;
esac

api_port="${api_binding##*:}"
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health"
echo
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/ready"
echo
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/app/" >/dev/null

if [[ -z "$("${compose[@]}" ps --status running --quiet worker)" ]]; then
  echo "Worker is not running." >&2
  exit 1
fi

"${compose[@]}" exec -T api alembic current
"${compose[@]}" ps

echo "Production smoke checks passed."
