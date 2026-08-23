#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${JOB_RADAR_PORT:?JOB_RADAR_PORT is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"

compose=(docker compose --env-file "$ENV_FILE")

port_in_use() {
  local port="$1"
  ss -ltnH "sport = :${port}" | grep -q .
}

service_is_running() {
  local service="$1"
  [[ -n "$("${compose[@]}" ps --status running --quiet "$service" 2>/dev/null || true)" ]]
}

check_binding() {
  local service="$1"
  local port="$2"

  if service_is_running "$service"; then
    echo "$service already running under Job Radar Compose; port $port may remain bound during upgrade."
    return 0
  fi

  if port_in_use "$port"; then
    echo "Port 127.0.0.1:$port is already in use by another process/service." >&2
    exit 1
  fi

  echo "Port 127.0.0.1:$port is available."
}

command -v docker >/dev/null
command -v ss >/dev/null
command -v curl >/dev/null

docker compose version >/dev/null
"${compose[@]}" config >/dev/null

check_binding api "$JOB_RADAR_PORT"
check_binding postgres "$POSTGRES_PORT"

echo "Job Radar production preflight passed."
