# Glitchy — Honest E-commerce Readiness Audit (2026)

**Scope:** an honest, non-marketing assessment of the store against the original brief and
against what a real, modern, professional e-commerce needs. **This is not a "production-ready"
sign-off.** Branch `release/staging-printify-fashion-store` (+ this fix branch). Verified on a
local Windows dev machine; **no real staging host exists**.

---

## 1. Were the original instructions met? (per area)

| Area | Status | Honest note |
|---|---|---|
| Logo | ✅ Done | Real "Glitchy" logo in navbar (light+dark) + footer; Italian tricolore accent in the first "G". |
| Premium design | ✅ Mostly | Consistent token system, premium components. Some legacy CSS duplication remains (theme.css has 3 cart blocks). |
| Responsive | ✅ Done | 375/390/1280/1440 verified, 0 overflow across the matrix. |
| Dark mode | ✅ Done | Systemic dark-mode pass; readable text/buttons/bands. (This audit's filter fix closes the last yellow-tint gap.) |
| Printify integration | ⚠️ Partial | Real READ data cached in DB for 2 products; **shipping is fallback**, push OFF, **variants stale** (live 18 vs site 12), no real orders. |
| Translations EN/IT/FR | ✅ Done | All customer-facing strings localized; FR `.po` corruption (made-on-demand) fixed. OpenAI translation cached for 1 product. |
| Cart | ✅ Done | Premium remove modal, transparent surfaces, qty stepper, coupon, free-ship, empty state. |
| Checkout | ⚠️ Partial | Works (guest + Stripe TEST), dark-aware. No step indicator / inline per-field errors / webhook tested on a public URL. |
| Variant dropdowns | ✅ Done | Vanilla sortx-style colour/size, no double-open. |
| Store filters | ✅ Done (this phase) | **Yellow hover root-caused and fixed**; no technical "Printify" category. |
| QA | ⚠️ Local only | 368 tests, 0 console/overflow/500 — but **all on localhost**, never on a public staging URL. |
| Security | ✅ Strong (dev) | No secrets in git, push/shipping/payments OFF. Key rotation still pending. |

## 2. What is genuinely COMPLETE
- Frontend UX/UI: navbar, footer, logo, home (de-duplicated), PDP, cart, collections, variant dropdowns, sort dropdown, draggable AI assistant, dark/light, mobile.
- i18n EN/IT/FR for all customer-facing copy; compiled, no corruption.
- Cart flows (add/remove-with-modal/qty/coupon/empty) and guest checkout to Stripe **TEST**.
- Test suite (368) green locally; `scripts/staging_check.sh` 0 failures.
- No customer-facing "Printify" category; filters/nav/sitemap use a public-only category manager; technical category 404s by URL.
- Filter "yellow hover" fixed at the real root cause (invalid `border-color:var(--border-strong)` shorthand + gold `accent-color` in dark).

## 3. What is PARTIAL
- **Printify data**: real but **cached** (not live-verified per request); a live audit showed **stale variant counts** (Printify 18 enabled vs site 12 buyable) → needs a re-sync.
- **Checkout**: functional but missing premium polish (step indicator, inline field errors, address autocomplete, saved-card UX) and a webhook test on a public URL.
- **Catalog**: only **2 real Printify products** (Sweet Dreams, New Day) + **3 demo/seed products** (ATX Jeans, RXN Blue Shirt, Great Tshirt — not synced, ~40% data quality).
- **OpenAI translations**: cached for **1 product only**; the rest fall back to clean English until a backfill is run with a (rotated) key.

## 4. What is LOCAL / DEV only
- The whole "QA live" so far is on `127.0.0.1:8799` with `DEBUG=True` and **sqlite**.
- No process manager, no served-by-gunicorn run, no WhiteNoise-in-prod verification.

## 5. What requires a REAL staging host
- A VPS/PaaS + **managed Postgres** + gunicorn + nginx + **HTTPS/domain**.
- `DJANGO_DEBUG=False`, real `DJANGO_ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`.
- Live QA on a **public URL** (current QA is localhost-only; this is the biggest unverified surface).
- Stripe **test webhook** exercised against the public URL.

## 6. What requires production / go-live
- **Rotate the exposed OpenAI + Printify keys**, then flip `OPENAI_KEY_ROTATED` / `PRINTIFY_KEY_ROTATED` to True (today both **False = NEEDS_ACTION**).
- Decide and configure **real shipping** (`SHIPPING_USE_PRINTIFY` is OFF → fallback table today).
- Real SMTP / n8n automation (today **not configured**).
- Production payment review (Stripe live keys, fraud/3DS, refunds), PayPal if wanted (today **disabled**).

## 7. What remains to be a great MODERN e-commerce
- A real, broad **catalog** synced from Printify (not 2 real + 3 demo).
- **Live shipping rates** + accurate delivery estimates per country.
- **Order lifecycle**: real Printify order push (currently OFF by design), tracking, returns automation, transactional emails.
- **Account area** depth: order history detail, re-order, saved cards, address book polish.
- **Search** quality (currently keyword + facets; no typo-tolerance/synonyms/relevance ranking).
- **Analytics/CRO**: real GA4/consent, A/B, abandoned-cart, reviews ingestion (no real reviews today).
- **Performance/SEO** at scale: image CDN, caching, structured data coverage, Lighthouse on the public URL.
- **CI/CD + PR workflow**: there is **no `main` branch** on the remote and no CI.

## 8. What is still DEMO / FALLBACK
- Stock value **9999** (hardcoded placeholder, not real inventory).
- **Shipping = fallback** rate table (not live Printify), because `SHIPPING_USE_PRINTIFY=False`.
- 3 **demo/seed products** with no Printify costs/gallery/provider.
- Product **reviews**: none real (cards show "New" instead of a rating).
- `base_cost` used when a variant has no `production_cost`.

## 9. What is REAL from Printify
- For 2 products: blueprint/provider ids, variant set, per-variant costs (cached), cleaned description, downloaded gallery images, title, visibility — all **read-only, cached from a prior sync**. Verified by a read-only `printify_data_audit`. No write/order/push ever occurred.

## 10. What must NOT be shown to customers (and isn't)
- Internal Printify IDs, blueprint/provider ids, production costs, base_cost, margins — verified **0 leaks** on the PDP.
- The technical **"Printify" category** — now removed and excluded from filters/nav/sitemap; direct URL 404s.
- Admin-only `data_quality` scores and sync status.

## 11. Main RISKS
1. **Exposed keys not rotated** — the OpenAI + Printify credentials were shared earlier; until rotated, any deploy is a credential risk. (Gates are correctly blocking.)
2. **No public-URL QA** — everything verified on localhost; real-host issues (HTTPS mixed content, ALLOWED_HOSTS, static via nginx/WhiteNoise, Stripe webhook) are unverified.
3. **Stale Printify data** — the catalog can drift from Printify (variants/prices) without a re-sync; a customer could see fewer/wrong variants.
4. **Thin catalog** — 2 real products is not a sellable store.
5. **No CI / no `main`** — no automated gate before merges; release branch is the only remote branch.

## 12. Next 10 priority interventions
1. Provision a real staging VPS + Postgres + nginx + **HTTPS** and deploy `release/staging-printify-fashion-store`.
2. **Rotate** OpenAI + Printify keys; set the two rotation gates True.
3. Run a full **Printify product re-sync** to fix stale variants (read-only; push stays OFF) and grow the catalog.
4. Decide shipping: turn `SHIPPING_USE_PRINTIFY=True` on staging to validate **live rates** (orders still not pushed).
5. **Public-URL QA**: re-run the full matrix (375/390/1280/1440 · EN/IT/FR · dark/light) on the staging domain; test the **Stripe test webhook**.
6. Backfill **OpenAI translations** for all products (cached, hash-invalidated).
7. Configure **SMTP/n8n** and verify transactional emails (order confirm, return updates).
8. Replace **demo products** with real synced products; remove placeholders.
9. Add **CI** (GitHub Actions: check/migrations/test) and create a **`main`** base branch + PR flow.
10. Checkout polish: inline field validation, step indicator, real reviews ingestion, basic analytics/consent.

---

**Bottom line (honest):** the storefront **code and UX are in good, premium shape and fully green locally**, and the two issues raised this phase (no "Printify" category; yellow filter hover) are **fixed at the root cause**. But the site is **NOT production-ready**: there is **no real staging host**, **no public-URL QA**, the **keys are unrotated**, **shipping is fallback**, the **catalog is mostly demo with 2 real (stale) Printify products**, and **n8n/SMTP/PayPal/CI/main are not set up**. It is ready for **human code review and for provisioning a real staging environment** — not for go-live.
