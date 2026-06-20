#!/usr/bin/env bash
# Smoke + health check for a staging (or local production-like) deployment.
# Usage: bash scripts/staging_check.sh https://staging.yourbrand.com
set -u
BASE="${1:-http://127.0.0.1:8799}"
echo "== Smoke check against: $BASE =="

PUBLIC="/ /it/ /fr/ /store/ /it/store/ /cart/ /returns/ /it/returns/ /fr/returns/ \
/accounts/login/ /it/accounts/login/ /accounts/register/"

fail=0
check() {
  code=$(curl -s -k -o /dev/null -w '%{http_code}' --max-time 15 "$BASE$1")
  if [ "$code" != "$2" ]; then
    echo "  FAIL [$code, expected $2] $1"; fail=$((fail+1))
  else
    echo "  ok   [$code] $1"
  fi
}

echo "-- public pages (expect 200) --"
for p in $PUBLIC; do check "$p" 200; done

echo "-- admin requires login (expect 302 redirect) --"
check "/admin/" 302

echo "-- n8n inbound requires signature/header (expect 401) --"
code=$(curl -s -k -o /dev/null -w '%{http_code}' --max-time 15 \
  -X POST -H 'Content-Type: application/json' -d '{"from_email":"x@y.z"}' \
  "$BASE/api/n8n/incoming-email/")
[ "$code" = "401" ] && echo "  ok   [401] /api/n8n/incoming-email/ (protected)" \
  || { echo "  FAIL [$code, expected 401] /api/n8n/incoming-email/"; fail=$((fail+1)); }

echo "-- stripe webhook rejects unsigned (expect 400) --"
code=$(curl -s -k -o /dev/null -w '%{http_code}' --max-time 15 \
  -X POST -H 'Content-Type: application/json' -d '{}' "$BASE/orders/stripe/webhook/")
[ "$code" = "400" ] && echo "  ok   [400] /orders/stripe/webhook/ (rejects unsigned)" \
  || { echo "  FAIL [$code, expected 400] /orders/stripe/webhook/"; fail=$((fail+1)); }

echo "== Result: $fail failure(s) =="
exit $fail
