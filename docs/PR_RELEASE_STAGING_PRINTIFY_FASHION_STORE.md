# PR — Release staging: premium Printify fashion store

**Title:** Release staging: premium Printify fashion store with n8n, Stripe, staging package and UI rebrand

**Source branch:** `release/staging-printify-fashion-store`
**Recommended target:** `main` or `staging` — **to be confirmed** against the real repository (no git remote is configured locally yet).
**Head commit at preparation time:** `a0a9aff`

> Local-only preparation. **No production deploy. No remote push performed.** `PRINTIFY_PUSH_ENABLED=False`.

---

## Summary
This release integrates the full build of the **Glitchy** Printify fashion store: backend hardening + integrations (Phases 1–5), the staging deployment package (Phase 6), and a complete premium UI/UX rebrand with regression fixes and a real-device acceptance gate (Phases 7–12). History is linear (fast-forwarded into `release/staging`).

## Phases integrated
| Phase | Content |
|---|---|
| 1 | Printify store: real cost/shipping/margin, guest checkout, 14-day returns, EN/IT/FR i18n, n8n integration layer |
| 2 | Hardening: secret externalization, complete Stripe webhook, real Printify sync + safe cost backfill |
| 3 | Integration dry run: real n8n + signed Stripe + complete order test |
| 4 | Pre-production: n8n native Header Auth, order.tracking fix, production settings, secret rotation docs |
| 5 | Release branch + staging env templates + deploy docs |
| 6 | Staging deployment package: systemd/nginx/gunicorn templates, deploy/health/backup/restore/secret-check scripts, n8n/Stripe/Printify runbooks |
| 7 | Premium fashion rebrand: design system, Pexels editorial hero, EN/IT/FR |
| 8 | Deep UI upgrade: SVG icon system, shop sidebar + mobile filter drawer, product-card hover/quick-view, PDP cross-sell + mobile sticky CTA, mobile nav drawer |
| 9 | Human-feedback fix: Plus Jakarta Sans font, navbar + high-contrast footer + newsletter rebuild, language selector, cache-busting, corrected translations |
| 10 | Final review micro-fixes: country select styling, summary chips, 4-up grids |
| 11 | Visual regression fix: **clickable mobile menu** (z-index/backdrop), working X close, footer social visibility, hero badge, responsive cards, premium order-detail, **visible animations** |
| 12 | Real-device acceptance gate: hit-tested menu, responsive sweep (7 breakpoints), 0 console errors |

## Security
- No secrets in tracked files or git history; all secrets via environment (`.env`, untracked).
- `.env` is git-ignored; `.env.staging.example` ships placeholders only.
- Pexels API key stored outside the repo, never committed/printed.
- Production hardening in `settings.py` under `if not DEBUG:` (HSTS, secure cookies, SSL redirect, referrer policy).
- Stripe webhook signature-verified + idempotent; n8n inbound protected (native Header Auth + HMAC observability).

## Printify
- Resilient client (retry/backoff), catalog/variant cost sync, safe cost backfill (real data only).
- **`PRINTIFY_PUSH_ENABLED=False`** in `.env` and staging template — **no real Printify orders are created**. Go-live conditions documented in `deploy/staging/printify-checklist.md`.

## Stripe
- Endpoint `/orders/stripe/webhook/`; events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `checkout.session.completed`, `charge.refunded`.
- Idempotent finalization, refund handling + margin-after-refund. Test keys for staging. Runbook: `deploy/staging/stripe-checklist.md`.

## n8n
- 11 importable workflows, native Header Auth (X-N8N-AUTH) as primary enforcement, HMAC as observability, SMTP fallback.
- Runbook: `deploy/staging/n8n-checklist.md`.

## Staging package
- `deploy/staging/`: gunicorn.service/.socket, nginx.conf, logrotate, systemd timers, env pointer, README + n8n/stripe/printify/rollback/backup-restore runbooks.
- `scripts/`: `deploy_staging.sh`, `health_check.sh`, `staging_check.sh`, `backup_staging.sh`, `restore_staging.sh`, `rotate_secrets_check.sh` (executable, secret-safe).

## UI/UX premium
- Palette ivory/espresso/champagne-gold/sage; **Plus Jakarta Sans** + Inter; SVG icon system; editorial Pexels hero.
- Premium navbar (wordmark + gold mark, language pill), high-contrast dark footer, newsletter band.
- Product cards (hover quick-view, responsive buttons), PDP (icon specs, cross-sell, mobile sticky CTA), premium order-detail (soft cards, thumbnails, icons).
- Mobile nav + filter drawers (accessible, scroll-lock, Esc/backdrop close). Visible motion respecting `prefers-reduced-motion`. Asset cache-busting via `ASSET_VERSION`.

## QA (local, real-click / hit-testing)
- Mobile menu fully clickable (links navigate; X/backdrop/Esc close) — verified EN + FR.
- Footer social visible (dark bg + light icon, gold hover); newsletter input not squished.
- Filter drawer clickable (category/Apply/Clear/close).
- **0 horizontal overflow** across 9 pages × 7 breakpoints (1440/1280/1024/768/430/390/375).
- **0 console errors** across 11 pages (EN/IT/FR). 0 HTTP 500. `prefers-reduced-motion` respected.

## Tests
- `manage.py check` ✅ · `makemigrations --check` (none) ✅ · `test` → **50 passed** ✅
- `compilemessages -l it -l fr` clean ✅ · `collectstatic --noinput` ✅ · `scripts/staging_check.sh` 0 failures ✅

## Remaining real issues
1. Admin retains native Django styling (smoke-tested, not re-skinned — deliberate).
2. Logo is a CSS wordmark + gold mark; a real brand logo asset would be better.
3. Staging go-live still needs real credentials (n8n/Stripe/IMAP), secret rotation, host/TLS — does not block the PR.
4. Physical-device verification recommended before production.

## Reviewer checklist
- [ ] No secrets in the diff; `.env` not present.
- [ ] `PRINTIFY_PUSH_ENABLED=False` in `.env.staging.example`.
- [ ] `manage.py test` passes locally (50).
- [ ] Mobile menu opens and links are clickable (375/390).
- [ ] Footer social icons visible; newsletter input usable.
- [ ] EN/IT/FR render without layout breaks.
- [ ] Stripe webhook rejects unsigned (400); n8n inbound is protected.

## Staging deploy checklist (post-merge, separate step — NOT in this PR)
- [ ] Provision host (Python 3.13, Postgres, domain + TLS).
- [ ] `cp .env.staging.example .env`, fill real values, `chmod 600 .env`.
- [ ] `bash scripts/rotate_secrets_check.sh` (no placeholders, push disabled, distinct n8n secrets).
- [ ] Install systemd/nginx templates from `deploy/staging/`.
- [ ] `bash scripts/deploy_staging.sh` then `bash scripts/staging_check.sh https://STAGING_DOMAIN`.
- [ ] Connect n8n credentials + Stripe webhook; verify end-to-end.

## Confirmations
- ✅ `PRINTIFY_PUSH_ENABLED=False`.
- ✅ No production deploy performed or implied by this PR.
- ✅ No remote push performed during preparation.

---

## Manual push & PR commands (run once a remote URL is confirmed)
```bash
# 1. add the GitHub remote (replace with the real URL you provide)
git remote add origin <GITHUB_REPO_URL>

# 2. push the release branch (sets upstream)
git push -u origin release/staging-printify-fashion-store

# 3a. open a PR with the GitHub CLI (if installed + authenticated)
gh pr create \
  --base <main|staging> \
  --head release/staging-printify-fashion-store \
  --title "Release staging: premium Printify fashion store with n8n, Stripe, staging package and UI rebrand" \
  --body-file docs/PR_RELEASE_STAGING_PRINTIFY_FASHION_STORE.md

# 3b. or open the PR manually in the GitHub UI:
#     New Pull Request -> base: <main|staging>, compare: release/staging-printify-fashion-store
#     paste this file's content as the PR description.
```
