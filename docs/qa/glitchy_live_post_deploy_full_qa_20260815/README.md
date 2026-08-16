# Glitchy — Live production QA after deploy 9443e64

- **Env:** https://glitchy.graphics/ · commit `9443e64` · branch `release/staging-printify-fashion-store`
- **When:** 2026-08-15, ~18:33–19:30 UTC
- **Browser:** Chrome (automation) · desktop 1920×911 · dark+light · mobile 390 (popup-measured)
- **Server access:** none (SSH publickey denied) → journalctl/showmigrations not run by me; substituted HTTP + browser checks.
- **Admin session:** none, and passwords must not be typed → interactive admin QA (site-visuals upload, invite accept, admin A-Z) blocked; admin **security boundary** verified anonymously instead.

## Result: PASS with follow-ups. No P0. No 500s and no console errors on any page/flow tested.

## Findings
| ID | Sev | Area | Summary |
|----|-----|------|---------|
| F5 | P1 | Assistant / config | Support assistant tells customers to email placeholder `support@example.com`; same placeholder feeds contact/order notifications. Root: `SUPPORT_EMAIL` unset in prod env → falls back to placeholder (settings.py:407), injected into AI knowledge (retrieval.py:161). **Config fix (env), no code.** |
| F2 | P2 | Cart | Identical variant forks a duplicate cart line instead of qty++. Order-sensitive variation compare. **FIXED on branch + tests.** |
| F3 | P2 | Checkout totals | Estimate widget "Estimated total" excludes tax; differs from Order-summary "Grand total" by the tax. Relabel or include tax. |
| F1 | P3 | Home | "Choose your style" icon (spark) reads as a loading spinner. **FIXED on branch.** |
| F4 | P3 | PDP | Custom colour/size dropdown panel renders behind the SAVE/ADD-TO-CART buttons; top option occluded. z-index. |
| F6 | P3 | Assistant | `/contact/` escalation CTA suppressed for "grounded" answers, so payment/order queries never reach the contact page. |
| — | P4 | PDP | Hidden `atc-thumb` ships with empty src (counts as a broken image until the modal populates it; renders fine in use). |

## What passed
- Checkout **shipping sync** (the headline fix): IT/FR €9.30 · US €13.30 · BE €15.80 — estimate widget and Order summary agree; grand = subtotal+shipping+tax each time. Only Standard offered (prod uses local rate table) → no false Express promise.
- PDP colour→gallery (ProductColorImage), premium description, add-to-cart modal (correct variant thumbnail, Esc closes, focus returns), variant thumbnails persist in cart.
- Contact centre: premium form, honeypot + signed form_ts, honest inline validation, IT/FR fully translated.
- Responsive 390: no horizontal overflow, no broken images on 12 routes. Dark/light theme toggles cleanly.
- Admin/invite endpoints gated (302→login for anon); bad invite tokens 302/404, no 500; path traversal 404.

## Not done (needs go-ahead)
- Valid contact-form submission (would create ContactRequest + dispatch → possible real internal email; held per "fermati e segnala", and F5 means notifications go to a placeholder anyway).
- Interactive admin QA (site-visuals upload, invite accept, admin A-Z) — needs a superadmin session I can't create.
- Payment sandbox — stopped before payment (no card entered).

## Screenshots
`home-desktop-premium.png` · `add-to-cart-modal.png` · `cart-duplicate-variant-rows-BUG.png` (F2) · `checkout-shipping-sync-us.png` (sync PASS + F3; customer PII redacted) · `contact-page-desktop.png` · `contact-validation-errors.png` · `assistant-support-email-placeholder-BUG.png` (F5)

## Fixes on branch `qa/glitchy-live-post-deploy-full-qa-20260815` (NOT pushed)
- `af84337` fix: merge identical cart variants (F2) + regression tests
- `ede9bd6` fix: swap the spinner-like step icon (F1)
- Full suite green: 1155 tests OK. Target branch untouched at 9443e64.
