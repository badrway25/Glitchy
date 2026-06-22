# Integrations Activation Runbook

Step-by-step to switch each integration from dev/sandbox to real. Never commit `.env`;
never paste secrets into chat, code or logs. Verify each with
`python manage.py integration_status` (safe statuses only).

## 1. OpenAI (assistant)
1. Revoke the current (exposed) key at platform.openai.com/api-keys.
2. Create a new **project-scoped** key with a hard monthly spend limit.
3. Put it in the staging `.env` as `AI_API_KEY` (only there).
4. Set `OPENAI_KEY_ROTATED=True`.
5. `bash scripts/rotate_secrets_check.sh` → 0 failures.
   *Fallback:* set `AI_ASSISTANT_ENABLED=False` to ship without the assistant.

## 2. Stripe
1. Start in **test** mode (`sk_test_…`/`pk_test_…`); confirm a test checkout end-to-end.
2. Add a webhook endpoint in the Stripe dashboard → `https://<host>/orders/stripe/webhook/`.
3. Copy its signing secret into `STRIPE_WEBHOOK_SECRET` (signature is verified server-side).
4. Switch to **live** keys only when go-live is approved; re-test one real low-value order.

## 3. PayPal
- Default is **disabled** and fail-closed (no order can be marked paid without verification).
- To enable: set `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `PAYPAL_API_BASE` (sandbox→live), `PAYPAL_ENABLED=True`.
- The `/payments/` endpoint then verifies the capture (amount + currency + COMPLETED) before finalising.

## 4. Printify
1. Set `PRINTIFY_API_TOKEN` + `PRINTIFY_SHOP_ID`.
2. Admin → **Refresh Printify status** / product sync (captures production costs).
3. Real shipping: `SHIPPING_USE_PRINTIFY=True` → quotes return `source=printify`.
4. Order push stays **dry-run** (`PRINTIFY_PUSH_ENABLED=False`) until explicitly authorised. Flip to `True` only when you intend to send real orders to the supplier.
5. Historical costs: `python manage.py backfill_order_costs` (dry-run) → review → `--apply`.

## 5. n8n
1. Set `N8N_WEBHOOK_BASE_URL` + `N8N_HEADER_AUTH_SECRET` (and `N8N_SHARED_SECRET` for inbound HMAC).
2. Import the workflows; set `N8N_ENABLED=True`.
3. Inbound endpoints require a valid `X-Signature` (HMAC) — verified; otherwise 401.
   *Fallback:* with n8n off, transactional email uses the SMTP fallback.

## 6. SMTP / Gmail / IMAP
1. Set `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` (app password), `EMAIL_USE_TLS=True`.
2. Keep `EMAIL_SMTP_FALLBACK=True` so email still sends if n8n is unavailable.
3. Send a test order-paid email and confirm delivery.

## 7. Database & security (prod)
- `DATABASE_URL` → Postgres. `DJANGO_DEBUG=False`. `DJANGO_ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` → real domain.
- `SITE_URL=https://<domain>` (drives canonical/sitemap/OG). Secure cookies + HSTS auto-enable when `DEBUG=False`.
