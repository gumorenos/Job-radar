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

if [[ ! "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "Retention days must be a non-negative integer." >&2
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
base_name="job-radar-${timestamp}"
if [[ -e "${BACKUP_DIR}/${base_name}.dump" ]]; then
  base_name="${base_name}-$$"
fi

tmp_file="${BACKUP_DIR}/.${base_name}.dump.tmp"
tmp_checksum="${BACKUP_DIR}/.${base_name}.dump.sha256.tmp"
final_file="${BACKUP_DIR}/${base_name}.dump"
checksum_file="${final_file}.sha256"
compose=(docker compose --env-file "$ENV_FILE")

cleanup() {
  rm -f "$tmp_file" "$tmp_checksum"
}
trap cleanup EXIT

"${compose[@]}" config >/dev/null
"${compose[@]}" exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp_file"

if [[ ! -s "$tmp_file" ]]; then
  echo "Backup is empty." >&2
  exit 1
fi

# Cheap archive validation before publishing the files. The full disposable
# restore drill happens after the dump and checksum sidecar are atomically named.
cat "$tmp_file" | "${compose[@]}" exec -T postgres pg_restore -l >/dev/null

mv "$tmp_file" "$final_file"
chmod 600 "$final_file"

checksum="$(sha256sum "$final_file" | awk '{print $1}')"
printf '%s  %s\n' "$checksum" "$(basename "$final_file")" > "$tmp_checksum"
mv "$tmp_checksum" "$checksum_file"
chmod 600 "$checksum_file"

bash ops/verify_backup.sh "$ENV_FILE" "$final_file" "$checksum_file"

find "$BACKUP_DIR" -type f \
  \( -name 'job-radar-*.dump' -o -name 'job-radar-*.dump.sha256' \) \
  -mtime "+${RETENTION_DAYS}" -delete

trap - EXIT
printf 'BACKUP_OK dump=%s checksum=%s\n' "$final_file" "$checksum_file"
