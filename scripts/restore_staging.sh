#!/usr/bin/env bash
# Restore Postgres DB and/or media from a backup. DESTRUCTIVE — requires --yes.
# Reads DATABASE_URL from .env (never printed).
# Usage:
#   bash scripts/restore_staging.sh --db backups/db-YYYY...sql.gz --yes
#   bash scripts/restore_staging.sh --media backups/media-YYYY...tar.gz --yes
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"; cd "$APP_DIR"
DB_FILE=""; MEDIA_FILE=""; CONFIRM="no"
while [ $# -gt 0 ]; do
  case "$1" in
    --db) DB_FILE="$2"; shift 2;;
    --media) MEDIA_FILE="$2"; shift 2;;
    --yes) CONFIRM="yes"; shift;;
    *) echo "unknown arg: $1"; exit 2;;
  esac
done

if [ "$CONFIRM" != "yes" ]; then
  echo "Refusing to run without --yes (this OVERWRITES data). Aborting."; exit 3
fi

if [ -n "$DB_FILE" ]; then
  [ -f "$DB_FILE" ] || { echo "DB file not found: $DB_FILE"; exit 4; }
  DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
  if [ -n "$DB_URL" ] && command -v psql >/dev/null 2>&1; then
    echo "==> restoring Postgres from $DB_FILE"
    gunzip -c "$DB_FILE" | psql "$DB_URL" -v ON_ERROR_STOP=1 >/dev/null
  else
    echo "FATAL: DATABASE_URL/psql required for restore"; exit 5
  fi
fi

if [ -n "$MEDIA_FILE" ]; then
  [ -f "$MEDIA_FILE" ] || { echo "media file not found: $MEDIA_FILE"; exit 6; }
  echo "==> restoring media from $MEDIA_FILE"
  tar -xzf "$MEDIA_FILE"
fi

echo "==> restore complete. Run migrations + smoke check:"
echo "    ./env/bin/python manage.py migrate --noinput && bash scripts/health_check.sh"
