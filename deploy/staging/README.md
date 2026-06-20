# greatkart — Staging Deployment Package

Operational artifacts for deploying the staging environment. **No production
deploy. No real Printify orders.** `PRINTIFY_PUSH_ENABLED` stays `False` in staging.
All files here use **placeholders only** — never commit real secrets.

## Contents
| File | Purpose |
|---|---|
| `gunicorn.service.template` | systemd unit for the app server |
| `gunicorn.socket.template` | optional unix-socket activation |
| `nginx.conf.template` | TLS reverse proxy + static/media serving |
| `logrotate.conf.template` | optional file-log rotation |
| `systemd-timers.example` | n8n-retry + printify-pull background jobs |
| `env.example` | pointer to `/.env.staging.example` (single source of truth) |
| `n8n-checklist.md` | n8n staging setup + test runbook |
| `stripe-checklist.md` | Stripe webhook staging runbook |
| `printify-checklist.md` | Printify staging runbook (push disabled) |
| `backup-restore.md` | DB + media backup/restore runbook |
| `rollback.md` | rollback runbook |

Scripts (repo `scripts/`): `deploy_staging.sh`, `health_check.sh`,
`staging_check.sh`, `backup_staging.sh`, `restore_staging.sh`,
`rotate_secrets_check.sh`.

Canonical docs (repo `docs/`): `STAGING_DEPLOY.md` (full guide),
`SECURITY_ROTATION.md` (secrets + pre-deploy checklist), `STAGING_READINESS.md`.

## Quick start (on the staging host, as the app user)
```bash
# 1. code + venv + deps
git checkout release/staging-printify-fashion-store
python3.13 -m venv env && . env/bin/activate && pip install -r requirements-staging.txt
# 2. env
cp .env.staging.example .env && chmod 600 .env   # fill REAL values
bash scripts/rotate_secrets_check.sh              # verify no placeholders / policy
# 3. systemd + nginx (replace __PLACEHOLDERS__ in deploy/staging/*.template)
sudo cp deploy/staging/gunicorn.service.template /etc/systemd/system/greatkart-staging.service
sudo cp deploy/staging/nginx.conf.template /etc/nginx/sites-available/greatkart-staging
# edit both, enable nginx site, `nginx -t`
sudo systemctl daemon-reload && sudo systemctl enable --now greatkart-staging
sudo systemctl reload nginx
# 4. first deploy (migrate, i18n, static, reload, health)
bash scripts/deploy_staging.sh
# 5. public smoke
bash scripts/staging_check.sh https://STAGING_DOMAIN
```

## Hard rules
- `DJANGO_DEBUG=False`, `PRINTIFY_PUSH_ENABLED=False`.
- `.env` chmod 600, owned by app user, never committed.
- Rotate all secrets before go-live (`docs/SECURITY_ROTATION.md`).
