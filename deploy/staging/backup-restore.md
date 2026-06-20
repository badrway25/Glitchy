# Backup & Restore Runbook (staging)

Scripts: `scripts/backup_staging.sh`, `scripts/restore_staging.sh`.
They read `DATABASE_URL` from `.env` and **never print** secrets.

## Backup
```bash
bash scripts/backup_staging.sh
# -> ./backups/db-<ts>.sql.gz  and  ./backups/media-<ts>.tar.gz
# retention: keeps the newest BACKUP_RETENTION (default 14) of each kind
```
Schedule (systemd timer or cron), e.g. nightly:
```
0 2 * * *  cd /srv/greatkart && bash scripts/backup_staging.sh
```
Ship `backups/` off-box (object storage) for durability.

## Restore (DESTRUCTIVE — requires `--yes`)
```bash
# DB
bash scripts/restore_staging.sh --db backups/db-<ts>.sql.gz --yes
# Media
bash scripts/restore_staging.sh --media backups/media-<ts>.tar.gz --yes
# then
./env/bin/python manage.py migrate --noinput
bash scripts/health_check.sh
```

## `.env` (secrets) — manual, NEVER in git or DB dumps
- Keep `.env` in an **encrypted** secret manager / vault, separate from DB/media
  backups. The backup scripts intentionally do **not** include `.env`.
- To rebuild a host: provision → `cp .env.staging.example .env` → restore secret
  values from the vault → `chmod 600 .env`.

## Retention & testing
- Retention: 14 daily (default), plus weekly/monthly off-box if required.
- **Test restores quarterly** on a throwaway staging DB to prove backups are valid.
- Verify a restore with `manage.py showmigrations` + `staging_check.sh`.

## Postgres notes
- `pg_dump --no-owner --no-privileges` is used so dumps restore cleanly into a
  fresh role/db.
- Ensure the target DB exists and the `DATABASE_URL` role can create objects.
