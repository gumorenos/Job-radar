#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
BACKUP_DIR="${2:-/srv/job-radar/backups}"
RETENTION_DAYS="${3:-14}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp_file="${BACKUP_DIR}/.job-radar-${timestamp}.dump.tmp"
final_file="${BACKUP_DIR}/job-radar-${timestamp}.dump"
compose=(docker compose --env-file "$ENV_FILE")

cleanup() {
  rm -f "$tmp_file"
}
trap cleanup EXIT

"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp_file"

if [[ ! -s "$tmp_file" ]]; then
  echo "Backup is empty." >&2
  exit 1
fi

cat "$tmp_file" | "${compose[@]}" exec -T postgres pg_restore -l >/dev/null
mv "$tmp_file" "$final_file"
chmod 600 "$final_file"
trap - EXIT

find "$BACKUP_DIR" -type f -name 'job-radar-*.dump' -mtime "+${RETENTION_DAYS}" -delete

echo "$final_file"
