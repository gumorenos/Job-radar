#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROD_ENV="${1:-$ROOT_DIR/.env.production}"
OPENCLAW_ROOT="${OPENCLAW_ROOT:-/home/ubuntu/.openclaw/workspace}"
OPENCLAW_SCRIPT="$OPENCLAW_ROOT/scripts/job_radar_sync.py"
OPENCLAW_ENV="$OPENCLAW_ROOT/config/job-radar.env"
TRACKING_DIR="$OPENCLAW_ROOT/tracking/agentmail-vacancies"
STATE_PATH="$TRACKING_DIR/job-radar-sync-state.json"
MARKER="# JOB_RADAR_BRIDGE_MANAGED"

if [[ "$OPENCLAW_ROOT" == /home/ubuntu/* && "$(id -un)" != "ubuntu" ]]; then
  echo "Run the bridge installer as user ubuntu so it uses the correct OpenClaw workspace." >&2
  exit 1
fi

command -v crontab >/dev/null
command -v python3 >/dev/null
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "OpenClaw bridge requires Python 3.11 or newer." >&2
  exit 1
}

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

existing_not_before=""
if [[ -f "$OPENCLAW_ENV" ]]; then
  existing_not_before="$(sed -n 's/^JOB_RADAR_SYNC_NOT_BEFORE=//p' "$OPENCLAW_ENV" | tail -n 1)"
fi
not_before="${existing_not_before:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

mkdir -p "$OPENCLAW_ROOT/scripts" "$OPENCLAW_ROOT/config" "$TRACKING_DIR"
install -m 0755 "$ROOT_DIR/ops/openclaw_job_radar_sync.py" "$OPENCLAW_SCRIPT"

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

if crontab -l 2>/dev/null | grep -Fq "$MARKER"; then
  cron_status="already enabled; existing managed cron entry preserved"
else
  cron_status="disabled; run ops/enable_openclaw_bridge.sh only after canary QA"
fi

printf 'Installed Job Radar OpenClaw bridge files without changing crontab.\n'
printf 'Cutoff: %s\n' "$not_before"
printf 'Crontab backup: %s\n' "$backup_path"
printf 'Bridge cron: %s\n' "$cron_status"
printf 'Existing vacancy scripts and Notion sync were not modified.\n'
