# Release / Staging Readiness — Final (2026)

Consolidated state of `release/staging-printify-fashion-store` after merging all readiness
work (Phases 18–28) via fast-forward.

## Branch state
- Target: `release/staging-printify-fashion-store` @ Phase-28 HEAD
- Merge: **fast-forward, no conflicts** (59 commits integrated)
- Working tree: clean · no GitHub remote configured · nothing pushed/deployed

## What's included
- **E-commerce**: wishlist/save-for-later, coupons (anti-abuse, idempotent redemption),
  reviews (verified purchase + rating distribution), product + general FAQ, size guide,
  recently-viewed, structured data.
- **Growth/merchandising**: smart recommendations, complete-the-look/outfit builder,
  collections, style quiz, notify-me, first-party analytics.
- **Discovery**: advanced shop filters (real, combinable, shareable URLs, chips, mobile
  drawer), premium search autocomplete + dedicated mobile search overlay, unified no-results.
- **AI assistant**: contextual, guard-railed, EN/IT/FR, shopping-mode.
- **P0 fixes**: PayPal fail-closed, fulfilment emails, WhiteNoise static, realistic catalogue.
- **P1**: SEO (sitemap/robots/canonical/hreflang/OG), legal pages + cookie consent (GDPR),
  refund idempotency, in-site tracking, admin PII masking.
- **Integrations readiness (code + mock tests)**: Stripe webhook (signed, idempotent),
  PayPal safe mode, Printify shipping fallback, Printify push gating, n8n/SMTP fallback.
- **Ops**: `integration_status`, `credential_readiness_check.sh`, `prodlike_check.sh`,
  dry-run cost backfill, staging checklist + activation runbooks, `.env.production.example`.

## Tests / QA
- 201 automated tests green · `check` + `check --deploy` clean (except SECRET_KEY, set in prod env).
- Live QA: 0 console errors, 0 HTTP 500, 0 overflow @375/390, EN/IT/FR.

## Safety posture (held)
- `PRINTIFY_PUSH_ENABLED=False` · `SHIPPING_USE_PRINTIFY=False` · PayPal disabled (fail-closed).
- No secret in git/history · `.env` untracked · OpenAI key rotation **deferred to the last step**.

## What remains MANUAL (owner/ops)
GitHub remote + push/PR · staging deploy + Postgres · Stripe credentials + public webhook ·
Printify token + real shipping/push activation · n8n + SMTP/Gmail credentials · live transaction
test · **OpenAI key rotation (final step)** · legal review.

## What remains STAGING / PRODUCTION
- Staging: real credentials, Postgres, deploy, public Stripe webhook, real shipping test.
- Production: live keys, real transaction test, DEBUG=False + real SECRET_KEY/domain, monitoring.

## Recommended operating order
1. Push branch + open PR → 2. Provision staging (Postgres) + deploy → 3. Stripe test→live + webhook →
4. Printify sync + shipping + (authorised) push → 5. n8n/SMTP → 6. Live QA on staging →
7. **OpenAI rotation (last)** → 8. Go-live decision.
