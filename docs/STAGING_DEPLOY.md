# Staging Deployment Guide

Target: a **staging** environment that mirrors production but uses **test** Stripe
keys, **disabled** Printify push, and a separate domain. No production deploy and
no real Printify orders until staging is green and explicitly authorized.

Branch to deploy: **`release/staging-printify-fashion-store`**.

> ⚠️ **Release note (2026-06-28, Phase 51/52 — pre-order shipping estimates):** this
> release adds DB migration **`printify_integration/0003_printifyshippingestimatecache`**
> (additive: a new `PrintifyShippingEstimateCache` table). The next deploy is **NOT a
> simple restart** — it must run:
> ```bash
> git pull                       # or fetch + checkout the release branch
> python manage.py migrate       # REQUIRED — applies 0003
> python manage.py collectstatic --noinput
> # restart gunicorn, then live QA
> ```
> Keep `PRINTIFY_PUSH_ENABLED=False`. Enable `SHIPPING_USE_PRINTIFY=True` **only** in a
> controlled staging environment (live shipping estimate is read-only — it never creates
> an order); leave it `False` at rest.

---

## 0. Prerequisites on the staging host
- Linux host, Python 3.13, PostgreSQL 14+, a domain `staging.yourbrand.com` with TLS.
- A reachable n8n instance (e.g. `n8n-staging.yourbrand.com`).
- Outbound HTTPS to `api.printify.com`, `api.stripe.com`.

## 1. Code + virtualenv
```bash
git clone <repo> greatkart && cd greatkart
git checkout release/staging-printify-fashion-store
python3.13 -m venv env
. env/bin/activate
pip install -U pip
pip install -r requirements-staging.txt   # runtime + gunicorn + psycopg + whitenoise
```

## 2. Environment
```bash
cp .env.staging.example .env
# Edit .env with REAL staging values (never commit it). Generate the three
# self-managed secrets, distinct from each other:
python -c "import secrets;print(secrets.token_urlsafe(64))"   # DJANGO_SECRET_KEY
python -c "import secrets;print(secrets.token_urlsafe(48))"   # N8N_HEADER_AUTH_SECRET
python -c "import secrets;print(secrets.token_urlsafe(48))"   # N8N_SHARED_SECRET
```
Required staging vars: `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (Postgres), `SITE_BASE_URL`,
`N8N_ENABLED=True`, `N8N_WEBHOOK_BASE_URL`, `N8N_HEADER_AUTH_SECRET`,
`N8N_SHARED_SECRET`, Stripe **test** keys + `STRIPE_WEBHOOK_SECRET`,
`PRINTIFY_API_TOKEN`, `PRINTIFY_SHOP_ID`, **`PRINTIFY_PUSH_ENABLED=False`**.

## 3. Database, i18n, static
```bash
python manage.py migrate
python manage.py compilemessages -l it -l fr
python manage.py collectstatic --noinput
python manage.py createsuperuser   # for /admin
```

## 4. App server (gunicorn)
```bash
gunicorn greatkart.wsgi:application --bind 127.0.0.1:8001 --workers 3 \
  --timeout 60 --access-logfile - --error-logfile -
```
Static is served by WhiteNoise (already wired when `whitenoise` is installed), so
nginx only needs to reverse-proxy. `/media/` should be served by nginx/object
storage in production.

## 5. Reverse proxy (nginx, abridged)
```nginx
server {
  listen 443 ssl;
  server_name staging.yourbrand.com;
  # ssl_certificate ...; ssl_certificate_key ...;
  client_max_body_size 16m;
  location /media/ { alias /srv/greatkart/media/; }
  location / {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;     # matches SECURE_PROXY_SSL_HEADER
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_pass http://127.0.0.1:8001;
  }
}
```

## 6. Health & smoke checks
```bash
bash scripts/staging_check.sh https://staging.yourbrand.com
```
Manual smoke (browser): Home EN/IT/FR, product detail (More), guest checkout,
order-complete, account dashboard, returns, admin Orders KPI / Returns /
Notifications-n8n / Printify SyncLog. Expect **0 HTTP 500, 0 console errors,
0 mobile overflow**.

## 7. n8n (staging) — see `n8n/EMAIL_SETUP.md`
- Import the 11 workflows from `n8n/workflows/` (`Settings → Import from File`).
- Create the **`Glitchy n8n Header Auth`** credential: header `X-N8N-AUTH`, value
  = `N8N_HEADER_AUTH_SECRET`. Attach to all webhook nodes.
- Create **`Glitchy Gmail`** (SMTP/OAuth2) + **`Glitchy Support Mailbox`** (IMAP)
  credentials; attach to the send/trigger nodes.
- Activate all webhook workflows (10); `Support Inbox Ingest` stays inactive until
  the mailbox credential is set.
- Set n8n env: `N8N_SHARED_SECRET`, `DJANGO_BASE_URL`, `ADMIN_NOTIFY_EMAIL`,
  `SUPPORT_EMAIL`.

## 8. Stripe (staging) — test mode
- Register a webhook endpoint `https://staging.yourbrand.com/orders/stripe/webhook/`
  for: `payment_intent.succeeded`, `payment_intent.payment_failed`,
  `checkout.session.completed`, `charge.refunded`.
- Put its signing secret in `.env` `STRIPE_WEBHOOK_SECRET`.
- Local forward (dev): `stripe listen --forward-to 127.0.0.1:8001/orders/stripe/webhook/`.

## 9. Printify (staging) — push DISABLED
- `PRINTIFY_PUSH_ENABLED=False` (mandatory in staging).
- Verify connectivity + costs:
  `python manage.py printify_check` · `python manage.py printify_sync_products --limit 50`.
- A test order's `printify_status` must be `push_disabled` (no real Printify order).

## 10. Background jobs (recommended)
Schedule (cron/systemd timers):
```bash
*/10 * * * * python manage.py n8n_retry --limit 50
*/30 * * * * python manage.py printify_pull_orders --limit 20
```

---
See `docs/SECURITY_ROTATION.md` for the secret rotation + pre-deploy checklist.
