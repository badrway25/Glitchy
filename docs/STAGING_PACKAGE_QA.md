# Staging Deploy Package — Local QA

Branch `ops/staging-deploy-package`. Verifies the deploy package without deploying.

## Static checks
- All `scripts/*.sh` pass `bash -n` (0 syntax errors).
- Secret scan over `deploy/` + `scripts/` → **0** real-secret patterns.
- `.env` not tracked; `.env.staging.example` placeholders only.
- Scripts marked executable in git (mode `100755`).

## App checks
- `manage.py check` → no issues.
- `makemigrations --check --dry-run` → no changes.
- `manage.py test` → **50 passed**.
- `compilemessages -l it -l fr` → 0 errors.
- `collectstatic --noinput` → ok.
- `check --deploy` (DEBUG=False) → only the dev `SECRET_KEY` warning (rotate before deploy).

## Smoke (against the running app)
- `scripts/health_check.sh` → 0 failures (`/`, `/it/`, `/fr/` 200; `/admin/` 302;
  `/api/n8n/incoming-email/` 405 on GET = alive + POST-only).
- `scripts/staging_check.sh` → 0 failures (public 200, admin 302, n8n inbound 401,
  stripe webhook 400 on unsigned).

## Visual
- Home / store EN/IT/FR render; **0 console errors**; premium design loads.

## Verdict
Deploy package is **complete and safe** (placeholders only, push disabled). Ready
to copy templates onto a real staging host and run `deploy_staging.sh` +
`staging_check.sh`.
