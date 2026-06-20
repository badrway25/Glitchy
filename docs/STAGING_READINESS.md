# Staging Readiness — Local Verification

Branch: `release/staging-printify-fashion-store` (linear chain of Phases 1–4).
No real staging host was available, so verification was done **locally in a
production-like mode** (`DJANGO_DEBUG=False`, `--insecure` to serve static like
WhiteNoise would, media intentionally unserved).

## Build / config checks
- `manage.py check` → no issues.
- `manage.py makemigrations --check --dry-run` → no changes.
- `manage.py test` → **50 passed**.
- `compilemessages -l it -l fr` → 0 errors.
- `collectstatic --noinput` → 375 files collected, no errors.
- `check --deploy` (DEBUG=False) → only the dev `SECRET_KEY` warning (rotate before deploy).

## Production-like run (DEBUG=False)
- Confirmed `settings.DEBUG=False`, `SECURE_HSTS_SECONDS=31536000`, secure cookies,
  `SECURE_PROXY_SSL_HEADER` active.
- `scripts/staging_check.sh` → **0 failures**: all public pages 200, `/admin/` 302,
  `/api/n8n/incoming-email/` 401 (protected), `/orders/stripe/webhook/` 400 (rejects unsigned).
- Browser (Italian, `/it/`): **premium design + CSS/JS loaded**, translations correct,
  **no static 404s**. Only `/media/photos/*.jpg` returned 404 — **expected**: under
  `DEBUG=False` Django does not serve media; nginx/object storage serves `/media/`
  in real staging (see `STAGING_DEPLOY.md` §5).

## Integration (verified across Phases 3–4, against real local n8n + signed Stripe)
- Django → n8n: all key events delivered (`sent`/200), including `order.tracking_available`.
- n8n → Django: 200 (valid), 401 (invalid), message-id dedup, order auto-link.
- Stripe webhook: 400 (unsigned), finalize, **idempotent** on redelivery, refund recorded.
- Header Auth: Django sends `X-N8N-AUTH`; enforcing endpoint accepts (200) / rejects (403).
- Printify: connected, costs synced; dry-run order `printify_status=push_disabled`
  (no real Printify order). `PRINTIFY_PUSH_ENABLED=False`.

## Verdict
- **Ready for STAGING: YES** — deploy to a staging host, wire n8n/Stripe/Printify
  credentials per the checklists, run `staging_check.sh` against the HTTPS URL.
- **Ready for PRODUCTION: NOT YET** — requires green staging + secret rotation +
  real n8n email credentials + public Stripe webhook + explicit authorization to
  set `PRINTIFY_PUSH_ENABLED=True`.
