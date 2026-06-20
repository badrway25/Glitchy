#!/usr/bin/env bash
# Quick liveness check against the app server (gunicorn bind, no nginx/static).
# Usage: bash scripts/health_check.sh [base_url]   (default http://127.0.0.1:8001)
set -u
BASE="${1:-http://127.0.0.1:8001}"
fail=0
chk() {
  code=$(curl -s -k -o /dev/null -w '%{http_code}' --max-time 10 "$BASE$1")
  if [ "$code" != "$2" ]; then echo "  FAIL [$code != $2] $1"; fail=$((fail+1));
  else echo "  ok   [$code] $1"; fi
}
echo "== health check: $BASE =="
chk "/" 200
chk "/it/" 200
chk "/fr/" 200
chk "/admin/" 302
chk "/api/n8n/incoming-email/" 405   # GET not allowed (endpoint alive, POST-only)
echo "== $fail failure(s) =="
exit $fail
