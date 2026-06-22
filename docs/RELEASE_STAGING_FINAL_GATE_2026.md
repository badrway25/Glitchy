# Release Gate — Final (2026)

Final surgical gate for `release/staging-printify-fashion-store` @ `9f40425+`.
Goal: confirm the branch is ready to publish on GitHub and take to staging **manually**.
No push, no deploy, no key rotation, no real Printify orders.

## Verdict at a glance
- Human review: **YES** · Push/PR: **YES** · Staging (code): **YES**
- Staging (manual): **NO — see remaining manual steps** · Production: **NO — see gaps**

## Feature matrix

| Area | Status |
|------|--------|
| **Core e-commerce** — home, shop, PDP, cart, guest checkout, Stripe (test), coupons, wishlist, verified reviews, FAQ, size guide, order detail, tracking, returns/refunds (14d) | ✅ OK |
| **Discovery** — premium search + autocomplete + no-results, advanced filters, collections index + detail, mood/season filtered landing, style quiz, recommendations, complete-the-look, recently-viewed, notify-me | ✅ OK |
| **Printify** — product/variant/image metadata, persisted shipping profiles, print areas/placeholders, dashboard 2.1, margin simulator + margin-after-refund, product completeness, safe CLI, shipping `source=printify` readiness | ✅ OK (push **disabled**) |
| **Printify push / real shipping in prod** | 🟠 manual/staging (credentials + authorisation) |
| **AI** — guard-railed assistant, Product Expert, collection discovery, no cost/ID leak, EN/IT/FR | ✅ OK |
| **Admin/Ops** — PII masking, Printify dashboard, collections admin + completeness, product quality, `integration_status`, `credential_readiness_check`, dry-run backfill, runbooks | ✅ OK |
| **SEO/Legal** — sitemap, robots, canonical, hreflang, OG/Twitter, JSON-LD, Privacy/Terms/Cookie + consent | ✅ OK |
| **OpenAI + Printify key rotation** | 🟠 manual (deferred to the last step; gates enforce it) |
| **Stripe live / public webhook / n8n / SMTP / Postgres / deploy** | 🟠 manual/staging (real credentials + host) |

## Tests (this gate)
- `check` ✅ · `check --deploy` (prod-like) → only SECRET_KEY W009 (set in prod env) ✅
- `makemigrations --check` (none) ✅ · `test` → **265 OK** ✅ · `compilemessages` clean ✅ · `collectstatic` ✅
- `staging_check.sh` 0 failures ✅ · `integration_status --staging` → exit 1 (correctly blocks on the 2 key rotations) ✅
- `product_audit --json` (no PII) ✅ · `printify_sync_shipping_profiles --dry-run --json` (no secrets) ✅

## Live QA (local)
- 11 customer pages × {375, 390, 1280}px × {EN, IT, FR}: **0 overflow, 0 console errors, 0 HTTP 500**.
- Customer pages: **0 leaks** (no blueprint/provider/cost/internal IDs), **0 raw HTML** in descriptions.
- All public URLs 200; admin URLs 302 (login-gated, correct).

## Security audit
- `.env` untracked (0) · OpenAI key 0 in files+history · Printify token 0 in files+history.
- No real Stripe/PayPal/webhook secret in git (only `sk_live_YOUR_…` placeholder in `.env.production.example`).
- `PRINTIFY_PUSH_ENABLED=False` · `SHIPPING_USE_PRINTIFY=False` · PayPal disabled · Stripe **test** mode.
- Rotation gates active for OpenAI **and** Printify (both flagged NEEDS_ACTION; not executed).

## Remaining (honest)
- **Code**: none blocking. Optional UX (collection hero-image upload, dedicated mood/season routes).
- **Credentials**: Stripe live + webhook, Printify (rotate exposed token), n8n + SMTP/Gmail.
- **Staging**: GitHub remote + push/PR, host + Postgres, deploy, `SHIPPING_USE_PRINTIFY=True` (staging .env), real shipping/email/checkout tests, Printify web-dashboard QA (owner login).
- **Production**: live keys, real transaction test, `DEBUG=False` + real SECRET_KEY/domain, monitoring.
- **Manual (last)**: rotate OpenAI + Printify keys → `credential_readiness_check.sh --staging` green → go-live.
