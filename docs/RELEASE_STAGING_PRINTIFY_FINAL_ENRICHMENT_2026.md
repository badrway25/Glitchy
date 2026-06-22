# Release / Staging — Printify Final Enrichment (2026)

State of `release/staging-printify-fashion-store` after consolidating the deep Printify
enrichment (Phases 30–33) plus the two pre-merge polish fixes.

## Branch
- Target: `release/staging-printify-fashion-store` @ Phase-33 HEAD
- Merge: **fast-forward, no conflicts** (24 commits integrated: Phases 30–33)
- Working tree clean · no GitHub remote · nothing pushed/deployed

## Pre-merge polish fixes (Phase 33)
- **Printify description sanitized**: raw HTML (`<p>/<br>/<ul>/<li>`) was shown to customers.
  `clean_printify_description()` converts it to safe plain text (bullets + line breaks, scripts
  stripped) at sync time; PDP renders via `linebreaksbr`; `meta_description()` is a clean
  single-line string for JSON-LD/SEO; `clean_product_descriptions` command fixes old rows.
  Plain-text output → no XSS surface; AI context gets clean text.
- **Mobile save button**: FR "Enregistrer" overflowed on 375/390. `.pdp-actions` now wraps,
  the wishlist button no longer shrinks below its label, and phones stack the actions
  full-width. Verified EN/IT/FR @375/390, no overflow.
- **i18n correction**: de-fuzzed `Printed to order`, the made-on-demand sentence and the
  `%(s)s size` plural (were English/"sold").

## Printify capability (integrated)
- **Product/variant/image metadata** mapped from the real payload (sku, cost, grams,
  enabled/available/default; image position, variant_ids, mockup).
- **Persistent shipping profiles** (`PrintifyShippingProfile`, per blueprint/provider/country:
  US $3.99 / EU $10 / AU $12.49 / CA $9.39, ETA, source).
- **Print areas/placeholders** (`PrintifyPrintArea`: position, has_print_file, missing-file flag).
- **Dashboard** `/admin/printify-dashboard/` 2.1 — KPIs, data quality, products/variants tables,
  persisted shipping matrix, print-area coverage, masked ids (staff-only, no PII).
- **Margin simulator** + **margin-after-refund** (full/partial/shipping, negative warning).
- **Data-quality score** + completeness audit; **CLI** with dry-run/apply/json/country/product-id.
- **Customer**: "Made on demand" (colours/sizes counts, ETA, returns) — never exposes
  ids/costs/margins/raw metadata. **AI Product Expert** with clean description + colours/sizes.

## Tests / QA
- **238 automated tests green** · `check --deploy` clean (except SECRET_KEY, set in prod env).
- Live: 0 console errors, 0 HTTP 500, 0 overflow @375/390, EN/IT/FR.

## Safety posture (held)
- `PRINTIFY_PUSH_ENABLED=False` · `.env SHIPPING_USE_PRINTIFY=False` · PayPal disabled · Stripe test.
- No secret in git/history (AI key + Printify token: 0 commits) · `.env` untracked.
- OpenAI **and** Printify key rotation gates active — **rotation deferred to the last step**.

## Remaining MANUAL (owner/ops)
GitHub remote + push/PR · staging deploy + Postgres · Stripe credentials + public webhook ·
`SHIPPING_USE_PRINTIFY=True` in staging `.env` + `printify_sync_shipping_profiles --apply` ·
n8n + SMTP/Gmail credentials · live transaction test · QA the Printify **web** dashboard
(owner login) · **rotate OpenAI + Printify keys (final step)** · legal review.

## Remaining STAGING / PRODUCTION
- Staging: real credentials, Postgres, deploy, public Stripe webhook, real shipping/email test.
- Production: live keys, real transaction, DEBUG=False + real SECRET_KEY/domain, monitoring.

## Recommended order
1. Push branch + PR → 2. Provision staging (Postgres) + deploy → 3. Stripe test→live + webhook →
4. Printify shipping (`SHIPPING_USE_PRINTIFY=True` + sync profiles) → 5. n8n/SMTP → 6. Live QA →
7. **Rotate OpenAI + Printify (last)** → 8. Go-live decision.
