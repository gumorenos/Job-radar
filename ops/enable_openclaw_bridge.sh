#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_ROOT="${OPENCLAW_ROOT:-/home/ubuntu/.openclaw/workspace}"
OPENCLAW_SCRIPT="$OPENCLAW_ROOT/scripts/job_radar_sync.py"
OPENCLAW_ENV="$OPENCLAW_ROOT/config/job-radar.env"
TRACKING_DIR="$OPENCLAW_ROOT/tracking/agentmail-vacancies"
LOG_PATH="$TRACKING_DIR/job-radar-sync.log"
MARKER="# JOB_RADAR_BRIDGE_MANAGED"

if [[ "$OPENCLAW_ROOT" == /home/ubuntu/* && "$(id -un)" != "ubuntu" ]]; then
  echo "Run bridge activation as user ubuntu so it updates the correct crontab." >&2
  exit 1
fi

command -v crontab >/dev/null
command -v python3 >/dev/null

if [[ ! -x "$OPENCLAW_SCRIPT" ]]; then
  echo "Bridge script is missing or not executable: $OPENCLAW_SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$OPENCLAW_ENV" ]]; then
  echo "Bridge env is missing: $OPENCLAW_ENV" >&2
  exit 1
fi

env_mode="$(stat -c '%a' "$OPENCLAW_ENV")"
if [[ "$env_mode" != "600" ]]; then
  echo "Bridge env must be mode 600; found $env_mode." >&2
  exit 1
fi
if grep -q '^POSTGRES_PASSWORD=' "$OPENCLAW_ENV"; then
  echo "Bridge env must not contain PostgreSQL credentials." >&2
  exit 1
fi
if ! grep -q '^JOB_RADAR_API_URL=http://127\.0\.0\.1:8010/api/v1/ingestions/jobs$' "$OPENCLAW_ENV"; then
  echo "Bridge env does not point to the expected localhost Job Radar API." >&2
  exit 1
fi

mkdir -p "$TRACKING_DIR"
backup_dir="$OPENCLAW_ROOT/tracking/job-radar-bridge-backups"
mkdir -p "$backup_dir"
backup_path="$backup_dir/crontab-enable-$(date -u +%Y%m%dT%H%M%SZ).txt"
crontab -l >"$backup_path" 2>/dev/null || true
chmod 0600 "$backup_path"

temp_cron="$(mktemp)"
trap 'rm -f "$temp_cron"' EXIT
{
  crontab -l 2>/dev/null | grep -Fv "$MARKER" || true
  printf '%s\n' "* * * * * /usr/bin/python3 $OPENCLAW_SCRIPT --env $OPENCLAW_ENV >> $LOG_PATH 2>&1 $MARKER"
} >"$temp_cron"
crontab "$temp_cron"

managed_count="$(crontab -l | grep -Fc "$MARKER" || true)"
if [[ "$managed_count" != "1" ]]; then
  echo "Expected exactly one managed bridge cron entry; found $managed_count." >&2
  exit 1
fi

printf 'Enabled Job Radar OpenClaw bridge cron.\n'
printf 'Crontab backup: %s\n' "$backup_path"
printf 'OpenClaw gateway and existing vacancy scripts were not modified.\n'
