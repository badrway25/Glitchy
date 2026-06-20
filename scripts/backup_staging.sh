#!/usr/bin/env bash
# Backup Postgres DB + media for greatkart staging.
# Reads DATABASE_URL from .env (never printed). Output: ./backups/
# Usage: bash scripts/backup_staging.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION="${BACKUP_RETENTION:-14}"        # keep last N of each kind
TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Pull DATABASE_URL without echoing it
DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"

if [ -n "$DB_URL" ] && command -v pg_dump >/dev/null 2>&1; then
  echo "==> dumping Postgres -> db-$TS.sql.gz"
  pg_dump "$DB_URL" --no-owner --no-privileges | gzip -9 > "$BACKUP_DIR/db-$TS.sql.gz"
else
  echo "==> DATABASE_URL empty or pg_dump missing — backing up SQLite if present"
  [ -f db.sqlite3 ] && gzip -9 -c db.sqlite3 > "$BACKUP_DIR/db-$TS.sqlite3.gz" || echo "  (no SQLite db)"
fi

# Media
if [ -d media ]; then
  echo "==> archiving media -> media-$TS.tar.gz"
  tar -czf "$BACKUP_DIR/media-$TS.tar.gz" media
fi

# Retention (keep newest N of each prefix)
prune() {
  ls -1t "$BACKUP_DIR"/$1* 2>/dev/null | tail -n +"$((RETENTION+1))" | xargs -r rm -f
}
prune "db-"
prune "media-"

echo "==> backups in $BACKUP_DIR:"
ls -1t "$BACKUP_DIR" | head -6
echo "NOTE: store .env separately + encrypted (NEVER in git, NEVER in these backups)."
