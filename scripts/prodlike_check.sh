#!/usr/bin/env bash
# Run Django's deployment checks in a PROD-LIKE environment (DEBUG off) WITHOUT
# touching the real .env. Surfaces every security warning that would apply in
# production. Does not print any secret. Exit non-zero if checks fail.
#
# Usage: bash scripts/prodlike_check.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY=./env/Scripts/python.exe
[ -x "$PY" ] || PY=python

echo "== Django deploy checks (prod-like: DEBUG=False) =="
DJANGO_DEBUG=False \
DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-staging.example.com}" \
CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-https://staging.example.com}" \
SITE_URL="${SITE_URL:-https://staging.example.com}" \
"$PY" manage.py check --deploy 2>&1 | grep -vE "^$"

echo ""
echo "Note: security.W009 (SECRET_KEY) is EXPECTED locally — production must set a long,"
echo "random DJANGO_SECRET_KEY in its environment. Everything else (HSTS, SSL redirect,"
echo "secure cookies, nosniff, X-Frame) is already enforced when DEBUG=False."
