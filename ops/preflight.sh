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

service_binding() {
  local service="$1"
  local container_port="$2"
  "${compose[@]}" port "$service" "$container_port" 2>/dev/null || true
}

check_binding() {
  local service="$1"
  local container_port="$2"
  local requested_port="$3"

  if service_is_running "$service"; then
    local binding
    local current_port
    binding="$(service_binding "$service" "$container_port")"
    current_port="${binding##*:}"
    if [[ -n "$binding" && "$current_port" == "$requested_port" ]]; then
      echo "$service already running under Job Radar Compose on $binding; upgrade binding accepted."
      return 0
    fi
  fi

  if port_in_use "$requested_port"; then
    echo "Port 127.0.0.1:$requested_port is already in use by another process/service." >&2
    exit 1
  fi

  echo "Port 127.0.0.1:$requested_port is available."
}

command -v docker >/dev/null
command -v ss >/dev/null
command -v curl >/dev/null

docker compose version >/dev/null
"${compose[@]}" config >/dev/null

check_binding api 8000 "$JOB_RADAR_PORT"
check_binding postgres 5432 "$POSTGRES_PORT"

echo "Job Radar production preflight passed."
