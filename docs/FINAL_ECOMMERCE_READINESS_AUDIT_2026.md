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
- **Store product-card gallery FIX + premium card features** (Phase 66): the carousel was
  unscrollable (`scroll-snap-align:center` on full-width slides + `x mandatory` pins
  `scrollLeft` to 0); fixed to `start` — arrow click now advances `0→308→616→924`, mobile
  swipe holds, dots update, no accidental PDP navigation (verified empirically, with a CSS
  regression-guard test). Added **colour/size swatches** on cards (real `Variation` data,
  prefetched → no N+1) and an honest **trust/delivery micro-panel**. 625 tests green, no
  migration. See `docs/STORE_GALLERY_INTERACTION_PREMIUM_FEATURES_2026.md`.
- **Luxury conversion + store/portal functional depth** (Phase 65): added a real,
  **safe "Buy again / Reorder"** (re-adds an order's items — with their original variations —
  to the cart only; never creates an order or takes payment; ownership-scoped; N+1-free), a
  **toast feedback system** (copy order number, wishlist add/remove on every surface),
  **elevated empty states**, and fixed three visual inconsistencies from owner feedback
  (subtle order-row buttons, truncated custom-select values, and a non-uniform button
  family — now all one premium size). The `CustomerActivityEvent` model was evaluated and
  **deliberately deferred** (the derived timeline already covers it without a risky
  migration). 614 tests green, no migration. See
  `docs/LUXURY_CONVERSION_STORE_PORTAL_FUNCTIONAL_DEPTH_2026.md`.
- **Ultra-premium page detail + motion polish** (Phase 64): six pages (wishlist, login,
  register, store, dashboard, address form) were elevated with a shared **premium page
  system** (editorial `.lux-head` headers, summary stat bars, luxury empty states) and a
  **refined motion layer** (staggered card reveal + KPI count-up, `prefers-reduced-motion`
  safe, no CLS). Login/register became a **split brand-panel layout** (register with four
  real benefit cards); the address form is now **grouped sections** with an elegant default
  switch; the wishlist gained an editorial header + summary bar. 604 tests green, no
  migration. See `docs/ULTRA_PREMIUM_PAGE_DETAIL_MOTION_POLISH_2026.md`.
- **Customer portal intelligence + wishlist facets + legacy sweep** (Phase 63): the
  wishlist gained **real, data-driven facets** (category, colour, size, price range,
  on-sale, multi-image, recently-saved) with quick chips, removable active chips,
  querystring + pagination, and **quick actions** (quick view / view / remove / sale price
  / multi-image carousel) — all ownership-scoped and **N+1-free**. The activity timeline
  now includes wishlist saves; the sidebar shows **lazy count badges** (orders/receipts/
  addresses); the **login/register pages were rebuilt premium** with a password toggle; and
  a copy-order-number utility was added. 593+ tests green, no migration. See
  `docs/CUSTOMER_PORTAL_INTELLIGENCE_WISHLIST_FACETS_2026.md`.
- **Premium customer portal + global polish** (Phase 62): the dashboard is now genuinely
  useful — **6 real KPI cards**, **quick actions**, **smart alerts**, a **recent-activity
  timeline derived from real data**, and a premium empty state; the order & billing lists
  gained **date-range / total-range / receipt** filters, **quick chips**, **result
  counts**, a collapsible advanced panel, and a billing **summary** — all
  querystring-persistent, pagination-preserving, mobile-friendly, **ownership-scoped**,
  and **N+1-free**. Wishlist sort + address search added. EN/IT/FR, light+dark, 573 tests
  green. No migration. See `docs/CUSTOMER_PORTAL_PREMIUM_UX_GLOBAL_POLISH_2026.md`.
- **Ultra-premium navbar buttons + store product-card image carousel** (Phase 61):
  the navbar `Login`/`Register` are now **equal-size** with a **premium gold
  Register** (sober gradient, not yellow) and an elegant soft Login (light+dark,
  mobile drawer); the global button system gained unified radius + `:disabled/
  :active/:focus-visible/loading` states + aligned icons + subtle reduced-motion-safe
  micro-motion. The big win: **multi-image products are now browsable directly in the
  store card** — a scroll-snap **carousel** (discreet desktop arrows, native mobile
  swipe, dots, keyboard) built on the already-prefetched `ProductImage` gallery
  (**no N+1**), capped at 5 images, with **no layout shift** and a clean single-image
  fallback. 560+ tests green. See
  `docs/ULTRA_PREMIUM_NAVBAR_BUTTONS_PRODUCT_CARD_GALLERY_2026.md`.
- **Post-deploy checkout-routing fix** (Phase 60): `/checkout/` (a non-route) now
  302-redirects to the real `/cart/checkout/`; smoke + tests added.
- **Premium frontend refinement + production-safe Printify sync + DB readiness**
  (Phase 59): a focused premium pass — **Fraunces serif** display font, softer
  palette (no pure black), centralized **`--container-max:1320px`** (navbar/footer
  width matched), a rebuilt **search split-pill** (flush integrated button, no radius
  defect), unified focus states, a new **"How Glitchy works"** section (EN/IT/FR) and
  a hero **rotating tagline** (reduced-motion safe). Backend: a **production-safe
  Printify sync** — a light `printify_sync_daemon_tick` (DB lock, tiny stale batch,
  request budget, persisted 429/5xx backoff; **never creates orders or publishes**;
  OFF by default), a `printify_sync_status` monitor, and documented systemd 30s timer
  templates. Plus a safe read-only `db_readiness_audit` (counts only, masked, no PII)
  and a backup-first DB transfer runbook. **539 tests green.** See
  `docs/PREMIUM_FRONTEND_SYSTEM_REFINEMENT_2026.md`,
  `docs/PRINTIFY_PRODUCTION_SYNC_30S_2026.md`, `docs/DB_TRANSFER_TO_SERVER_2026.md`.
  Also: **`ALLOWED_HOSTS` from env** (bare name first) so the server needs no local
  `settings.py` edit (clean working tree on deploy).
- **Premium dynamic homepage** (Phase 58): the homepage hero is now a **wide,
  full-bleed editorial** image (Pexels, optimized WebP+JPEG, art-directed mobile
  crop) with a refined gradient scrim, dual CTA, trust line, subtle Ken-Burns +
  scroll-driven parallax, and an elegant scroll cue. A new **"The Edit"** band maps
  three premium category cards (Shirts / T-shirts / Jackets) to **real** category
  pages, and the editorial split now uses a premium fabric shot. All imagery is
  **fetched by Pexels photo id** via a secure management command (key read from env,
  never printed; local assets only, no hotlink) and **documented + attributed** in
  `docs/image-sources/PEXELS_HOME_ASSETS_2026.md`. Motion is vanilla, reduced-motion
  safe; LCP hero is ~13 KB WebP. EN/IT/FR, light+dark, 375/390 verified. 511 tests
  green. See `docs/PREMIUM_DYNAMIC_HOMEPAGE_PEXELS_2026.md`.
- **Premium language switcher** (Phase 57): the navbar dropdown now shows the
  **language name only** (English / Italiano / Français — no "EN/IT/FR" codes) on a
  **flag-inspired full-width background** (green/white/red, blue/white/red, sober
  navy/white/red), CSS-only (no flag images), readable in light & dark, with gold
  selected ring + check, `aria-current`, and full-width mobile rendering. See
  `docs/PREMIUM_LANGUAGE_DROPDOWN_2026.md`.
- **Luxury store filters + motion** (Phase 56): the `/store` left rail is
  **redesigned** — editorial "Refine your look" header, **collapsible** sections
  (persisted), **circular colour swatches**, **size/rating pills**, **availability
  toggle switches**, premium currency price inputs, per-section count badges.
  Mobile filter is now a **bottom sheet** (drag handle, sticky Clear/Show-results
  footer, focus trap). Added **scroll-reveal motion** (IntersectionObserver,
  reduced-motion safe), **category editorial heroes**, and 2 smart features
  (**Continue your search** localStorage banner + real-category **smart empty
  state**). 482 tests green. See
  `docs/LUXURY_STORE_FILTERS_MOTION_EXPERIENCE_2026.md`.
- **Ultra-premium interaction polish** (Phase 55): checkout **step indicator**
  (Bag → Details → Payment) + sticky desktop summary; **Quick View focus trap**
  (full a11y); elegant **taupe button inversion** (sort + soft buttons, no more
  black/white-on-white); store badges moved **top-left** (no overlap with the
  wishlist heart); single-line mobile prices; generated **placeholder.png**
  (console 0). Active filter chips / mobile filter drawer / search-category
  connection verified (pre-existing). 463 tests green. See
  `docs/ULTRA_PREMIUM_FILTERS_CATEGORIES_CHECKOUT_2026.md`.
- **"Wow" polish + smart features** (Phase 54): real **Product Quick View**
  drawer (desktop) / bottom sheet (mobile) with delivery estimate + premium
  variant dropdowns; **search recent (localStorage) + popular (real categories)**;
  **price-proximity** recommendations + "Pairs well with" badge; heart-pop +
  `prefers-reduced-motion`; wishlist JS delegation. No new migration. 450 tests
  green. See `docs/WOW_ECOMMERCE_POLISH_SMART_FEATURES_2026.md`. (Size guide is
  generic — provider-specific charts still TODO.)
- **Premium customer portal** (Phase 53): dashboard (KPI bug fixed), orders with
  search/filter/sort + premium cards, **Billing & receipts** center, premium
  **PDF order receipt** (EN/IT/FR, logo, Paid/Pending, shipping line, preview +
  download), wishlist search, validated address book, and **site-wide premium
  dropdowns** (`premium-select.js`). **End-to-end tests** across BE/IT/FR/US + an
  unsupported-country edge, plus portal **data-isolation** tests (a user cannot
  see/download/delete another user's order/receipt/address). No new migration.
  See `docs/CUSTOMER_PORTAL_PREMIUM_E2E_2026.md`.
- Frontend UX/UI: navbar, footer, logo, home (de-duplicated), PDP, cart, collections, variant dropdowns, sort dropdown, draggable AI assistant, dark/light, mobile.
- i18n EN/IT/FR for all customer-facing copy; compiled, no corruption.
- Cart flows (add/remove-with-modal/qty/coupon/empty) and guest checkout to Stripe **TEST**.
- Test suite (368) green locally; `scripts/staging_check.sh` 0 failures.
- No customer-facing "Printify" category; filters/nav/sitemap use a public-only category manager; technical category 404s by URL.
- Filter "yellow hover" fixed at the real root cause (invalid `border-color:var(--border-strong)` shorthand + gold `accent-color` in dark).

## 3. What is PARTIAL
- **Pre-order shipping estimates** (Phase 51): the cart/checkout now show an
  estimated **cost + delivery window before checkout** via a 3-tier estimator
  (live Printify `orders/shipping.json` → cached catalog profile → local
  fallback). **Live mode is OFF by default** (`SHIPPING_USE_PRINTIFY=False`), so
  today estimates come from cached profiles / fallback; transit times are honest
  documented estimates (the API returns cost, not time). No order is created.
  See `docs/PRINTIFY_PREORDER_SHIPPING_ESTIMATES_2026.md`.
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
