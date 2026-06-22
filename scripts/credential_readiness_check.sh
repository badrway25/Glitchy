#!/usr/bin/env bash
# Staging credential readiness gate. Prints only safe statuses (never secret values)
# and exits non-zero if a staging-critical integration is not ready.
# Usage: bash scripts/credential_readiness_check.sh [--staging]
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./env/Scripts/python.exe
[ -x "$PY" ] || PY=python
exec "$PY" manage.py integration_status "${1:---staging}"
