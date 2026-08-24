#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_ROOT="${OPENCLAW_ROOT:-/home/ubuntu/.openclaw/workspace}"
OPENCLAW_SCRIPT="$OPENCLAW_ROOT/scripts/job_radar_sync.py"
OPENCLAW_ENV="$OPENCLAW_ROOT/config/job-radar.env"
MARKER="# JOB_RADAR_BRIDGE_MANAGED"

temp_cron="$(mktemp)"
trap 'rm -f "$temp_cron"' EXIT
crontab -l 2>/dev/null | grep -Fv "$MARKER" >"$temp_cron" || true
crontab "$temp_cron"

rm -f "$OPENCLAW_SCRIPT" "$OPENCLAW_ENV"
printf 'Removed Job Radar bridge cron entry, deployed script and dedicated secret file.\n'
printf 'State/log/history were preserved for audit and safe reinstall.\n'
