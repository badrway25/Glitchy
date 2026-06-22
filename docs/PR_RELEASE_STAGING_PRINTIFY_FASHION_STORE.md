# PR — Release/staging: premium Printify fashion e-commerce readiness

> Package for opening the pull request. Commands are **suggested, not executed** (no remote configured).

## Title
**Release/staging: premium Printify fashion e-commerce readiness**

## Summary
Brings `release/staging-printify-fashion-store` to a production-grade, staging-ready state for a
made-on-demand fashion store (Django + Stripe + Printify + n8n). Server-authoritative payments,
deep Printify enrichment, a premium storefront (search, collections, PDP), a guard-railed AI
assistant, full SEO/legal/GDPR, and operational tooling. All customer-facing text is EN/IT/FR.
No real orders, no live payments, no key rotation, and Printify push stays disabled.

## What's included
- **Core**: cart, guest checkout, **Stripe (test, signature-verified webhook)**, **PayPal fail-closed**,
  coupons (idempotent), verified reviews, FAQ, size guide, order detail, **in-site tracking**,
  returns/refunds (14d, idempotent accounting).
- **Discovery**: premium always-visible search + autocomplete, advanced filters, **collections**
  (index + premium detail + mood/season filtered landing), style quiz, recommendations,
  complete-the-look, recently-viewed, notify-me.
- **Printify (deep)**: product/variant/image metadata, **persisted shipping profiles**, **print
  areas/placeholders**, **admin dashboard 2.1**, **margin simulator + margin-after-refund**,
  product completeness, safe CLI (dry-run/apply/json), sanitized descriptions.
- **AI**: contextual assistant, Product Expert, collection discovery — never leaks costs/IDs.
- **Ops/Security**: admin PII masking, `integration_status`, `credential_readiness_check`,
  rotation gates (OpenAI + Printify), prod-like settings, runbooks.
- **SEO/Legal**: sitemap, robots, canonical, hreflang, OG/Twitter, JSON-LD, Privacy/Terms/Cookie + consent.

## Tests / QA
- **265 automated tests green** · `check --deploy` clean (except SECRET_KEY, set in prod env).
- Live: 0 console errors, 0 HTTP 500, 0 overflow @375/390/1280, EN/IT/FR, 0 customer-facing leaks.

## Risks
- Low for code. The risk surface is **activation**: live Stripe keys + public webhook, Printify
  real shipping/push, n8n/SMTP — all gated and off by default. The exposed OpenAI + Printify keys
  must be rotated before staging (enforced by `credential_readiness_check.sh --staging`).

## Remaining manual (not in this PR)
GitHub remote + deploy · Postgres · Stripe credentials + webhook · Printify token rotation +
real shipping/push · n8n + SMTP · live transaction test · **rotate OpenAI + Printify (last step)**.

## Rollback
- Pre-merge: branch is fast-forward only — `git checkout release/staging-printify-fashion-store && git reset --hard <prev-sha>`.
- Staging: redeploy the previous image/tag; `scripts/restore_staging.sh` for DB; no migration is destructive.

## Reviewer checklist
- [ ] `python manage.py test` → 265 pass
- [ ] `python manage.py check --deploy` → only SECRET_KEY warning
- [ ] No secret in diff; `.env` not tracked; `.env*.example` are placeholders only
- [ ] `PRINTIFY_PUSH_ENABLED=False`, `SHIPPING_USE_PRINTIFY=False`, Stripe test, PayPal disabled
- [ ] Customer pages: no internal IDs/costs/margins, no raw HTML; EN/IT/FR
- [ ] Legal pages reviewed by counsel before go-live

## Staging checklist (after merge/push)
See `STAGING_ACTIVATION_CHECKLIST.md` (20 steps) + `INTEGRATIONS_ACTIVATION_RUNBOOK.md`.

## No-secrets checklist
- [ ] `git ls-files | grep -x .env` → empty
- [ ] `git log -p --all -S sk-proj-` → empty · Printify JWT not in history
- [ ] Logs contain status codes + truncated errors only

## Suggested commands (NOT executed — no remote configured)
```bash
git remote add origin <YOUR_PRIVATE_REPO_URL>
git push -u origin release/staging-printify-fashion-store
# then open the PR from the GitHub UI, or with the gh CLI:
# gh pr create --base main --head release/staging-printify-fashion-store \
#   --title "Release/staging: premium Printify fashion e-commerce readiness"
```
