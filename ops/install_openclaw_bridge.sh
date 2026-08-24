#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROD_ENV="${1:-$ROOT_DIR/.env.production}"
OPENCLAW_ROOT="${OPENCLAW_ROOT:-/home/ubuntu/.openclaw/workspace}"
OPENCLAW_SCRIPT="$OPENCLAW_ROOT/scripts/job_radar_sync.py"
OPENCLAW_ENV="$OPENCLAW_ROOT/config/job-radar.env"
TRACKING_DIR="$OPENCLAW_ROOT/tracking/agentmail-vacancies"
STATE_PATH="$TRACKING_DIR/job-radar-sync-state.json"
LOG_PATH="$TRACKING_DIR/job-radar-sync.log"
MARKER="# JOB_RADAR_BRIDGE_MANAGED"

if [[ ! -f "$PROD_ENV" ]]; then
  echo "Missing Job Radar production env: $PROD_ENV" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/ops/openclaw_job_radar_sync.py" ]]; then
  echo "Bridge source is missing from the Job Radar checkout." >&2
  exit 1
fi

api_key="$(sed -n 's/^JOB_RADAR_API_KEY=//p' "$PROD_ENV" | tail -n 1)"
api_port="$(sed -n 's/^JOB_RADAR_PORT=//p' "$PROD_ENV" | tail -n 1)"
if [[ -z "$api_key" || -z "$api_port" ]]; then
  echo "Production env must define JOB_RADAR_API_KEY and JOB_RADAR_PORT." >&2
  exit 1
fi
if [[ "$api_port" != "8010" ]]; then
  echo "Expected production Job Radar port 8010; found $api_port." >&2
  exit 1
fi

mkdir -p "$OPENCLAW_ROOT/scripts" "$OPENCLAW_ROOT/config" "$TRACKING_DIR"
install -m 0755 "$ROOT_DIR/ops/openclaw_job_radar_sync.py" "$OPENCLAW_SCRIPT"

not_before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
umask 077
cat >"$OPENCLAW_ENV" <<EOF
JOB_RADAR_API_URL=http://127.0.0.1:8010/api/v1/ingestions/jobs
JOB_RADAR_API_KEY=$api_key
JOB_RADAR_TRACKING_DIR=$TRACKING_DIR
JOB_RADAR_SYNC_STATE_PATH=$STATE_PATH
JOB_RADAR_SYNC_NOT_BEFORE=$not_before
EOF
chmod 0600 "$OPENCLAW_ENV"

backup_dir="$OPENCLAW_ROOT/tracking/job-radar-bridge-backups"
mkdir -p "$backup_dir"
backup_path="$backup_dir/crontab-$(date -u +%Y%m%dT%H%M%SZ).txt"
crontab -l >"$backup_path" 2>/dev/null || true
chmod 0600 "$backup_path"

temp_cron="$(mktemp)"
trap 'rm -f "$temp_cron"' EXIT
{
  crontab -l 2>/dev/null | grep -Fv "$MARKER" || true
  printf '%s\n' "* * * * * /usr/bin/python3 $OPENCLAW_SCRIPT --env $OPENCLAW_ENV >> $LOG_PATH 2>&1 $MARKER"
} >"$temp_cron"
crontab "$temp_cron"

printf 'Installed Job Radar OpenClaw bridge.\n'
printf 'Cutoff: %s\n' "$not_before"
printf 'Crontab backup: %s\n' "$backup_path"
printf 'Existing vacancy scripts and Notion sync were not modified.\n'
