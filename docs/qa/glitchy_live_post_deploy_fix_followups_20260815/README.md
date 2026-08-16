# Glitchy — fix follow-ups QA (F3/F4/F5/F6 + F1/F2 verify)

Branch: `qa/glitchy-live-post-deploy-full-qa-20260815` (base `release/staging-printify-fashion-store @ 9443e64`).
Local browser QA (no deploy). Full suite after all fixes: **1183 tests OK**. Target branch untouched.

## Findings addressed
| ID | Fix | Verified |
| --- | --- | --- |
| F3 | Checkout estimate widget now shows Tax and the SAME grand total as the Order summary (Option A). Also fixed pre-existing i18n bug: "Discount" was "Account"/"Compte" → "Sconto"/"Remise". | Widget total €31.42 == Order-summary Grand total €31.42, Tax €0.52 shown; endpoint 200; test. |
| F4 | PDP variant dropdown given one coherent stacking layer (`--z-variant-dropdown:1150`): above CTA + mobile sticky CTA, below size guide, toasts and modals. The "behind the button" was the opacity fade-in, not z-order. | Size dropdown renders opaque over ADD TO CART; layer test. |
| F5 | Placeholder support email (`support@example.com`) never shown to customers; assistant routed to /contact/; non-blocking system check `glitchy.support.W001/W002`; config doc. No `.env` change, no secrets. | Legal page shows /contact/ (not the email); assistant answer carried no placeholder; tests. |
| F6 | Assistant always offers a Contact-support CTA for payment/order/delivery/returns/complaints, even when grounded; only the category travels in the URL; no product cards under a complaint. | "charged twice…refund" → CONTACT SUPPORT + /contact/?category=payment, 0 product cards, no placeholder email. |
| F1 | Home step-01 icon `spark` → `tag` (was spinner-like). | Icon is a tag (path+circle). |
| F2 | Identical variant merges to qty++ instead of duplicate row. | Add White/S twice → 1 row, qty 2. |

## Screenshots
- `home-step-icon-fixed.png` — F1: "Choose your style" tag icon
- `cart-duplicate-variant-merged.png` — F2: one row, qty 2
- `checkout-estimate-summary-consistent.png` — F3: Order summary Tax €0.52 + Grand €31.42 (widget total verified = grand; visible "Network error" is the local estimate rate-limiter from repeated QA calls, endpoint returned 200)
- `pdp-dropdown-layer-fixed.png` — F4: size dropdown opaque over ADD TO CART
- `assistant-payment-contact-cta.png` / `assistant-no-placeholder-email.png` — F6/F5: CONTACT SUPPORT + /contact/?category=payment, no product cards, no placeholder email (run with SUPPORT_EMAIL placeholder + AI mock for a deterministic capture)
- `contact-prefilled-category.png` — F6: /contact/?category=payment pre-selects "Payment problem"

## Responsive
390 & 768: no horizontal overflow on home, checkout (with the new Tax/Discount rows), PDP, contact. PDP `broken:1` is the hidden `atc-thumb` (empty src until the modal populates it), pre-existing.

## Not changed
No deploy, no push, no `.env` edit, no production flag change, no secrets printed. F5 requires the real email vars to be set in the server env (see `docs/PRODUCTION_CONFIGURATION_REQUIRED.md`).
