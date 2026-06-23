# Real Staging Deploy — Runbook & Status (Glitchy)

**Repo:** https://github.com/badrway25/Glitchy.git · **Branch:** `release/staging-printify-fashion-store`
**Deployable commit:** `218e932` · **Date:** 2026-06

> **STATUS: DEPLOY NOT EXECUTED — no staging host available.**
> The values supplied (`STAGING_HOST=<INSERIRE_HOST_O_IP>`, `STAGING_DOMAIN=<INSERIRE_DOMINIO_STAGING>`,
> `SSH_USER=<INSERIRE_UTENTE_SSH>`) are **placeholders**, and this machine is a local **Windows dev box**
> (no `gunicorn`/`nginx`/`systemctl`/`certbot`, DB is sqlite). Per the safety rules, no deploy was
> invented. Below is a precise, project-accurate handoff to run on a real Linux VPS.

---

## A. Local readiness (verified on `218e932`)
| Item | Status |
|---|---|
| Branch/remote in sync | ✓ `release/staging-printify-fashion-store` @ `218e932` |
| `manage.py check` | 0 issues |
| `makemigrations --check` | no drift |
| `manage.py test` | 356 passed |
| `compilemessages` | clean |
| `scripts/staging_check.sh` | 0 failures |
| Secrets in git | none (`.env*` ignored, no AI key / Printify token) |

## B. Project-specific facts (use these — the generic task template differs)
- **WSGI app:** `greatkart.wsgi:application`
- **Staging deps file:** `requirements-staging.txt` → `gunicorn>=22,<24`, `psycopg[binary]>=3.1,<4`, `whitenoise>=6.6,<7`
- **Static:** served by **WhiteNoise** (nginx static alias optional, still recommended)
- **DB:** built-in `DATABASE_URL` parser (no `dj-database-url` dependency) — set `DATABASE_URL=postgres://…`
- **Env loading:** settings read `os.environ`; `load_dotenv(".env")` is only a local fallback.
  On the host, systemd `EnvironmentFile=` injects the vars → works without a `.env` file.
- **⚠️ Correct env var NAMES** (the project does NOT use `DEBUG`/`SECRET_KEY`/`OPENAI_API_KEY`/`STRIPE_TEST_MODE`):
  - `DJANGO_DEBUG=False` (not `DEBUG`)
  - `DJANGO_SECRET_KEY=…` (not `SECRET_KEY`)
  - `DJANGO_ALLOWED_HOSTS=staging.domain,127.0.0.1,localhost` (not `ALLOWED_HOSTS`)
  - `AI_API_KEY=…` (not `OPENAI_API_KEY`)
  - Stripe uses `STRIPE_PUBLIC_KEY`/`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` (test keys); there is no `STRIPE_TEST_MODE` flag.
  - **Authoritative template:** copy `.env.staging.example` → `.env.staging` and fill real values (never commit).

## C. Deploy runbook (run on the Linux VPS as the deploy user)
```bash
# 0) prerequisites (Ubuntu/Debian): python3.12, venv, postgresql, nginx, certbot
sudo apt update && sudo apt install -y python3.12 python3.12-venv postgresql nginx certbot python3-certbot-nginx git

# 1) directory
sudo mkdir -p /srv/glitchy-staging && sudo chown -R "$USER":"$USER" /srv/glitchy-staging
cd /srv/glitchy-staging

# 2) clone the exact staging commit
git clone https://github.com/badrway25/Glitchy.git .
git checkout release/staging-printify-fashion-store
git pull --ff-only origin release/staging-printify-fashion-store
git rev-parse --short HEAD        # expect 218e932 or newer

# 3) virtualenv + deps (base + staging)
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt -r requirements-staging.txt

# 4) Postgres (set a strong password securely; do NOT echo it)
sudo -u postgres psql -c "CREATE DATABASE glitchy_staging;"
sudo -u postgres psql -c "CREATE USER glitchy_staging WITH PASSWORD '***';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE glitchy_staging TO glitchy_staging;"
sudo -u postgres psql -c "ALTER DATABASE glitchy_staging OWNER TO glitchy_staging;"

# 5) env (fill real values; keep OUT of git)
cp .env.staging.example .env.staging   # then edit; set DJANGO_DEBUG=False,
#   DATABASE_URL=postgres://glitchy_staging:***@127.0.0.1:5432/glitchy_staging
#   PRINTIFY_PUSH_ENABLED=False  (mandatory)  ·  SHIPPING_USE_PRINTIFY=True (read-only on staging)
#   Stripe TEST keys only · PAYPAL_ENABLED=False · AI_API_KEY=<staging key>
set -a; source .env.staging; set +a

# 6) Django bring-up
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py migrate
django-admin compilemessages -l it -l fr
python manage.py collectstatic --noinput
python manage.py test
bash scripts/staging_check.sh
```

## D. systemd service — `/etc/systemd/system/glitchy-staging.service`
```ini
[Unit]
Description=Glitchy Staging (gunicorn)
After=network.target postgresql.service

[Service]
User=<DEPLOY_USER>
Group=www-data
WorkingDirectory=/srv/glitchy-staging
EnvironmentFile=/srv/glitchy-staging/.env.staging
ExecStart=/srv/glitchy-staging/.venv/bin/gunicorn greatkart.wsgi:application --bind 127.0.0.1:8899 --workers 3 --timeout 60
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now glitchy-staging
sudo systemctl status glitchy-staging --no-pager
```

## E. nginx — `/etc/nginx/sites-available/glitchy-staging`
```nginx
server {
    listen 80;
    server_name <STAGING_DOMAIN>;
    client_max_body_size 12m;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    location /static/ { alias /srv/glitchy-staging/static/; access_log off; expires 30d; }
    location /media/  { alias /srv/glitchy-staging/media/; }
    location / {
        proxy_pass http://127.0.0.1:8899;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/glitchy-staging /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <STAGING_DOMAIN>          # HTTPS (DNS must point to the server)
curl -I https://<STAGING_DOMAIN>/                 # expect 200
curl -I https://<STAGING_DOMAIN>/static/css/premium.css
```

## F. Printify (read-only on staging — NO orders, NO product push)
```bash
python manage.py printify_sync_shipping_profiles --dry-run --json
python manage.py printify_sync_shipping_profiles --apply  --json   # writes shipping profile rows only
python manage.py printify_data_audit --compare-site --safe-output --json
python manage.py product_audit --json
```
`PRINTIFY_PUSH_ENABLED=False` stays mandatory. `SHIPPING_USE_PRINTIFY=True` only reads live rates.

## G. OpenAI translations (only if `AI_API_KEY` set on the host)
```bash
python manage.py translate_printify_descriptions --dry-run --all-languages --json
python manage.py translate_printify_descriptions --apply --all-languages --json   # cached, hash-invalidated
```
Without the key → PDP falls back to clean English (no in-request translation).

## H. Rotation gates (DO NOT rotate without explicit authorization)
- `OPENAI_KEY_ROTATED=False` → **NEEDS_ACTION**
- `PRINTIFY_KEY_ROTATED=False` → **NEEDS_ACTION**
- Both keys were exposed in chat earlier → rotate on the host, then set the gates to `True`.
  This is the **last step before go-live**; staging can be reviewed technically before this.

## I. Security
- `.env` / `.env.staging` never committed · AI key not in git · Printify token not in git · no secrets printed.
- `PRINTIFY_PUSH_ENABLED=False` · Stripe TEST only · PayPal disabled · no real order · no real payment.

## J. Go-live blockers (remaining, manual)
1. Provision the VPS + DNS for `<STAGING_DOMAIN>` (HTTPS via certbot).
2. Fill `.env.staging` with real values (Stripe test, Printify staging token, AI key, n8n/SMTP).
3. Run sections C–G on the host; live QA the matrix (375/390/1280/1440 · EN/IT/FR · light/dark).
4. Rotate OpenAI + Printify keys; flip the two gates.
5. (Optional) create a `main` base branch for a PR workflow.

**Staging review (code/QA): READY.** **Real staging: NOT deployed (no host).** **Production: NOT ready.**
