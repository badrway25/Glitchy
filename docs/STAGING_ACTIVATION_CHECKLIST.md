# Staging Activation Checklist

Run top-to-bottom to take the codebase from local to a real, safe staging environment.
Each gate has a command that prints **only safe statuses (never secret values)**.

> Staging stays **BLOCKED** until the OpenAI key is rotated (item 1) — by design.

| # | Step | Gate / command | Done when |
|---|------|----------------|-----------|
| 1 | **Rotate the OpenAI key** (exposed in chat) | `bash scripts/rotate_secrets_check.sh` | revoke old key, create new project-scoped key + spend limit, put in `.env`, set `OPENAI_KEY_ROTATED=True`; check passes |
| 2 | **GitHub remote** | `git remote -v` | a private remote is configured and you can push the branch |
| 3 | **Provision staging host + deploy** | `deploy/staging/README.md` | host reachable, app served by gunicorn |
| 4 | **Staging `.env`** from template | diff against `.env.staging.example` | all required keys set, no placeholders |
| 5 | **Postgres** (not SQLite) | `python manage.py integration_status` → Database = Postgres | `DATABASE_URL` set, migrations applied |
| 6 | **collectstatic + WhiteNoise** | `python manage.py collectstatic --noinput` | static served (gzip), 200 on `/static/css/premium.css` |
| 7 | **Stripe keys** | `integration_status` → Stripe OK | secret/public/webhook secret set (test first, then live) |
| 8 | **Stripe webhook (public URL)** | Stripe dashboard → add endpoint `/orders/stripe/webhook/` | signed events delivered, signature verified |
| 9 | **PayPal status** | `integration_status` → PayPal | DISABLED (safe) **or** server-verify configured (client id + secret) |
| 10 | **Printify sync** | admin → "Refresh Printify status" | products + costs synced (real token/shop) |
| 11 | **Printify real shipping** | set `SHIPPING_USE_PRINTIFY=True` | quotes return `source=printify` |
| 12 | **Printify push (dry-run first)** | keep `PRINTIFY_PUSH_ENABLED=False` | no real supplier order; flip to True only when authorised |
| 13 | **n8n workflows** | `integration_status` → n8n OK | base URL + header-auth secret set, workflows imported, healthy |
| 14 | **SMTP/Gmail/IMAP** | `integration_status` → Email OK | transactional email delivers (or SMTP fallback verified) |
| 15 | **Legal / GDPR** | open `/privacy/ /terms/ /cookies/` | pages reviewed by counsel; cookie banner shows |
| 16 | **SEO checks** | open `/sitemap.xml /robots.txt` | sitemap valid, canonical + hreflang present, `SITE_URL` = real domain |
| 17 | **Admin PII masking** | open admin lists | emails/phones masked in lists |
| 18 | **Live QA (browser)** | `deploy/staging/STAGING_PACKAGE_QA.md` | checkout/returns/tracking/assistant pass; 0 console/500 |
| 19 | **Rollback rehearsed** | `scripts/restore_staging.sh` | backup + restore verified |
| 20 | **Monitoring / logs** | host logging | error logs aggregated, no secrets in logs |

## One-shot readiness gate

```bash
bash scripts/credential_readiness_check.sh --staging   # exits non-zero if a critical item is missing
python manage.py integration_status                    # full human-readable report
bash scripts/staging_check.sh https://staging.example  # HTTP smoke + auth gating
```
