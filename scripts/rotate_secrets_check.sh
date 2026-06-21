#!/usr/bin/env bash
# Pre-deploy secret check. Verifies required secrets are present and NOT
# placeholders — WITHOUT printing any value. Run on the staging host.
# Usage: bash scripts/rotate_secrets_check.sh
set -u
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"; cd "$APP_DIR"
ENV_FILE="${ENV_FILE:-.env}"
fail=0

if git ls-files --error-unmatch "$ENV_FILE" >/dev/null 2>&1; then
  echo "FAIL: $ENV_FILE is tracked by git (must be ignored)"; fail=$((fail+1))
else echo "ok  : $ENV_FILE not tracked"; fi

val() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-; }

# required-and-must-not-be-placeholder
PLACEHOLDER_RE='change-me|GENERATE_|your-|YOUR_|xxx|REPLACE|STAGING_PRINTIFY_TOKEN|FROM_THE_|PROVIDER_APP_PASSWORD|0000000'
for k in DJANGO_SECRET_KEY DATABASE_URL STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
         PRINTIFY_API_TOKEN PRINTIFY_SHOP_ID N8N_HEADER_AUTH_SECRET N8N_SHARED_SECRET \
         N8N_WEBHOOK_BASE_URL DJANGO_ALLOWED_HOSTS; do
  v="$(val "$k")"
  if [ -z "$v" ]; then echo "FAIL: $k is empty"; fail=$((fail+1));
  elif printf '%s' "$v" | grep -qiE "$PLACEHOLDER_RE"; then echo "FAIL: $k still a placeholder"; fail=$((fail+1));
  else echo "ok  : $k set"; fi
done

# specific policy checks (compare lengths/flags, never echo values)
[ "$(val DJANGO_DEBUG)" = "False" ] && echo "ok  : DJANGO_DEBUG=False" || { echo "FAIL: DJANGO_DEBUG must be False"; fail=$((fail+1)); }
[ "$(val PRINTIFY_PUSH_ENABLED)" = "False" ] && echo "ok  : PRINTIFY_PUSH_ENABLED=False" || { echo "FAIL: PRINTIFY_PUSH_ENABLED must be False in staging"; fail=$((fail+1)); }
case "$(val DJANGO_SECRET_KEY)" in django-insecure-*) echo "FAIL: DJANGO_SECRET_KEY still dev key"; fail=$((fail+1));; *) echo "ok  : SECRET_KEY not dev key";; esac
if [ "$(val N8N_HEADER_AUTH_SECRET)" = "$(val N8N_SHARED_SECRET)" ]; then
  echo "FAIL: N8N_HEADER_AUTH_SECRET and N8N_SHARED_SECRET must differ"; fail=$((fail+1));
else echo "ok  : n8n header/shared secrets distinct"; fi

# OpenAI assistant key: when the assistant is enabled the key must be a real,
# freshly-rotated value (the dev key shared in chat must NOT reach staging/prod).
if [ "$(val AI_ASSISTANT_ENABLED)" = "True" ]; then
  AIK="$(val AI_API_KEY)"
  if [ -z "$AIK" ]; then echo "FAIL: AI_API_KEY empty while AI_ASSISTANT_ENABLED=True"; fail=$((fail+1));
  elif printf '%s' "$AIK" | grep -qiE "$PLACEHOLDER_RE"; then echo "FAIL: AI_API_KEY still a placeholder"; fail=$((fail+1));
  else echo "ok  : AI_API_KEY set (rotate before prod — dev key is exposed)"; fi
else
  echo "ok  : AI assistant disabled (AI_API_KEY not required)"
fi

echo "== $fail failure(s) =="
exit $fail
