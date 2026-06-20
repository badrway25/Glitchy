# Rollback Runbook (staging)

Goal: return to the last known-good release quickly and safely. Take a backup
**before** any risky deploy (`scripts/backup_staging.sh`).

## 1. Identify the target
```bash
git log --oneline -10            # find the last good commit/tag
PREV=<good-commit-sha-or-tag>
```

## 2. Roll back code
```bash
git checkout "$PREV"
./env/bin/pip install -r requirements-staging.txt
./env/bin/python manage.py check
```

## 3. Roll back migrations (only if the bad deploy added migrations)
> Reversible migrations only. If a migration is destructive/irreversible, restore
> the DB from backup instead (step 5).
```bash
# example: revert app 'orders' to the migration that shipped with $PREV
./env/bin/python manage.py migrate orders <previous_migration_name>
```
Inspect applied migrations: `./env/bin/python manage.py showmigrations`.

## 4. Static / translations
```bash
./env/bin/python manage.py compilemessages -l it -l fr
./env/bin/python manage.py collectstatic --noinput
```

## 5. Restore DB / media (only if data is corrupted)
```bash
bash scripts/restore_staging.sh --db backups/db-<good-ts>.sql.gz --yes
bash scripts/restore_staging.sh --media backups/media-<good-ts>.tar.gz --yes
```

## 6. Restart + verify
```bash
sudo systemctl restart greatkart-staging
bash scripts/health_check.sh
bash scripts/staging_check.sh https://STAGING_DOMAIN
```

## 7. In-flight Stripe / Printify during rollback
- **Stripe**: webhooks are **idempotent** and the finalize guard prevents double
  processing. Stripe auto-retries failed deliveries — once the app is healthy they
  reconcile. Do not manually re-finalize.
- **Printify**: push is `False` in staging, so no real orders exist to reverse.
  (In production, cancel any erroneously-created Printify order from the Printify
  dashboard before re-deploying.)
- **n8n**: failed outbound events stay `retrying`/`failed`; replay with
  `manage.py n8n_retry` after the app is healthy.

## 8. `.env` rollback
`.env` is host-local and untracked. If a config change caused the issue, restore
the previous `.env` from your encrypted secret store (never from git).
