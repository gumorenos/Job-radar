#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
DUMP_FILE="${2:-}"
CHECKSUM_FILE="${3:-${DUMP_FILE}.sha256}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

if [[ -z "$DUMP_FILE" || ! -f "$DUMP_FILE" ]]; then
  echo "Missing backup dump: ${DUMP_FILE:-<not provided>}" >&2
  exit 1
fi

if [[ ! -s "$DUMP_FILE" ]]; then
  echo "Backup dump is empty: $DUMP_FILE" >&2
  exit 1
fi

if [[ ! -f "$CHECKSUM_FILE" ]]; then
  echo "Missing checksum sidecar: $CHECKSUM_FILE" >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE")
"${compose[@]}" config >/dev/null

dump_dir="$(cd "$(dirname "$DUMP_FILE")" && pwd)"
dump_name="$(basename "$DUMP_FILE")"
checksum_dir="$(cd "$(dirname "$CHECKSUM_FILE")" && pwd)"
checksum_name="$(basename "$CHECKSUM_FILE")"

if [[ "$dump_dir" != "$checksum_dir" ]]; then
  echo "Checksum sidecar must be stored beside the dump." >&2
  exit 1
fi

if ! grep -Eq "^[0-9a-fA-F]{64}  ${dump_name//./\.}$" "$CHECKSUM_FILE"; then
  echo "Checksum sidecar has an unexpected format." >&2
  exit 1
fi

(
  cd "$dump_dir"
  sha256sum --check --status "$checksum_name"
)

# A readable archive catalog is necessary but not sufficient. Restore the full
# dump into a disposable database to prove PostgreSQL can consume it.
cat "$DUMP_FILE" | "${compose[@]}" exec -T postgres pg_restore -l >/dev/null

restore_db="jr_restore_$(date -u +%Y%m%d%H%M%S)_$$"
restore_created=0

cleanup_best_effort() {
  if [[ "$restore_created" -eq 1 ]]; then
    "${compose[@]}" exec -T postgres sh -c \
      'dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$restore_db" >/dev/null 2>&1 || true
  fi
}
trap cleanup_best_effort EXIT

"${compose[@]}" exec -T postgres sh -c \
  'createdb -U "$POSTGRES_USER" --template=template0 "$1"' sh "$restore_db"
restore_created=1

cat "$DUMP_FILE" | "${compose[@]}" exec -T postgres sh -c \
  'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$1"' \
  sh "$restore_db" >/dev/null

alembic_version="$(
  "${compose[@]}" exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -Atqc \
      "SELECT version_num FROM alembic_version LIMIT 1"' sh "$restore_db"
)"

if [[ -z "$alembic_version" ]]; then
  echo "Restored database has no Alembic version." >&2
  exit 1
fi

public_tables="$(
  "${compose[@]}" exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -Atqc \
      "SELECT count(*) FROM information_schema.tables WHERE table_schema = '\''public'\''"' \
    sh "$restore_db"
)"

core_tables="$(
  "${compose[@]}" exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -Atqc \
      "SELECT count(*) FROM information_schema.tables
       WHERE table_schema = '\''public'\''
         AND table_name IN ('\''candidate_profiles'\'', '\''ingestion_events'\'', '\''jobs'\'', '\''job_postings'\'', '\''match_analyses'\'')"' \
    sh "$restore_db"
)"

if [[ ! "$public_tables" =~ ^[0-9]+$ || "$public_tables" -lt 5 ]]; then
  echo "Restored database has an implausible public table count: $public_tables" >&2
  exit 1
fi

if [[ "$core_tables" != "5" ]]; then
  echo "Restored database is missing one or more core Job Radar tables." >&2
  exit 1
fi

if ! "${compose[@]}" exec -T postgres sh -c \
  'dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$restore_db" >/dev/null; then
  echo "Disposable restore database could not be removed: $restore_db" >&2
  exit 1
fi
restore_created=0
trap - EXIT

printf 'BACKUP_VERIFY_OK dump=%s checksum=verified alembic=%s public_tables=%s\n' \
  "$dump_name" "$alembic_version" "$public_tables"
