#!/usr/bin/env bash
# Idempotent staging deploy for greatkart. Run ON the staging host as the app user.
# Usage: bash scripts/deploy_staging.sh [git_ref]
# Requires: .env present (chmod 600), virtualenv at ./env, service greatkart-staging.
set -euo pipefail

REF="${1:-release/staging-printify-fashion-store}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="${GREATKART_SERVICE:-greatkart-staging}"
cd "$APP_DIR"

echo "==> greatkart staging deploy  (ref=$REF, dir=$APP_DIR)"

# 0. Safety: refuse to deploy if .env is missing or Printify push is enabled
if [ ! -f .env ]; then echo "FATAL: .env missing"; exit 2; fi
if grep -qE '^PRINTIFY_PUSH_ENABLED=True' .env; then
  echo "FATAL: PRINTIFY_PUSH_ENABLED=True is not allowed on staging. Aborting."; exit 3
fi

# 1. Code
echo "--> fetching code"
git fetch --all --quiet
git checkout "$REF" --quiet
git pull --ff-only --quiet || true

# 2. Dependencies
echo "--> installing dependencies"
./env/bin/pip install -q -r requirements-staging.txt

# 3. Sanity check BEFORE touching the DB
echo "--> manage.py check"
./env/bin/python manage.py check

# 4. Migrate, translations, static
echo "--> migrate"
./env/bin/python manage.py migrate --noinput
echo "--> compilemessages"
./env/bin/python manage.py compilemessages -l it -l fr
echo "--> collectstatic"
./env/bin/python manage.py collectstatic --noinput

# 5. Graceful reload
echo "--> reloading $SERVICE"
sudo systemctl reload "$SERVICE" 2>/dev/null || sudo systemctl restart "$SERVICE"

# 6. Health check
sleep 3
echo "--> health check"
bash scripts/health_check.sh "http://127.0.0.1:8001" || {
  echo "HEALTH CHECK FAILED — investigate (journalctl -u $SERVICE -n 100)"; exit 4; }

echo "==> deploy OK  ($(git rev-parse --short HEAD))"
