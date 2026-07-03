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
| Printify integration | ⚠️ Partial | **Admin-driven import now works** (Discover shops → Use this shop → Sync, local catalogue only, Phase 72). Still: **shipping is fallback**, push OFF, no real orders; the background daemon still reads the env token (follow-up). |
| Translations EN/IT/FR | ✅ Done | All customer-facing strings localized; FR `.po` corruption (made-on-demand) fixed. OpenAI translation cached for 1 product. |
| Cart | ✅ Done | Premium remove modal, transparent surfaces, qty stepper, coupon, free-ship, empty state. |
| Checkout | ⚠️ Partial | Works (guest + Stripe TEST), dark-aware. No step indicator / inline per-field errors / webhook tested on a public URL. |
| Variant dropdowns | ✅ Done | Vanilla sortx-style colour/size, no double-open. |
| Store filters | ✅ Done (this phase) | **Yellow hover root-caused and fixed**; no technical "Printify" category. |
| QA | ⚠️ Local only | 368 tests, 0 console/overflow/500 — but **all on localhost**, never on a public staging URL. |
| Security | ✅ Strong (dev) | No secrets in git, push/shipping/payments OFF. Key rotation still pending. |

## 2. What is genuinely COMPLETE
- **Premium home cards + secure Payment Control Center + admin i18n** (Phase 76): balanced the
  home trust cards (equal-height flex + line-clamp + an accessible native-`<dialog>` "Read more"
  modal). Added a `payments` app mirroring the Printify secure-config pattern:
  `PaymentProviderConfig` (Stripe + PayPal) with **Fernet-encrypted, write-only, masked** server
  secrets (`PAYMENT_CONFIG_KEY`), safe defaults (disabled/test/checkout-off/live-off,
  superadmin-gated), read-only **Test connection** (no charge/capture/refund), a
  DB-preferred/ENV-fallback credential resolver wired into Stripe + PayPal checkout
  (backward-compatible), and a `PaymentEvent` audit log. Wrapped the admin sidebar + labels in
  `gettext_lazy` and translated the admin chrome to it/fr (gettext-verified). Migration
  `payments/0001`; new env `PAYMENT_CONFIG_KEY`; deploy needs migrate. Admin live language-toggle
  + Arabic/RTL deferred (documented). See
  `docs/PREMIUM_HOME_PAYMENT_CONTROL_CENTER_ADMIN_I18N_2026.md`.
- **Store card carousel functional fix + premium filters** (Phase 75): root-caused (via
  screenshot diff) why the card "next" never changed the image — `.media-skeleton img` is
  `position:absolute`, so all carousel slides stacked; plus the main image (a content-duplicate
  of a gallery image) was prepended, making slides 0–1 identical. Fixed: slide img forced
  `position:static`, transform-based carousel (translateX + swipe + idempotent init), gallery-
  first `card_image_urls`. Refined the "Refine your look" filters: price focus ring now wraps
  the € + input, collapsed groups have real top-spacing when re-opened, colour selection is
  clearly premium (row wash + gold ring + ✓). No migration. See
  `docs/STORE_CAROUSEL_AND_FILTER_SYSTEM_FINAL_FIX_2026.md`.
- **Store visual interaction fixes + Glitchy favicon** (Phase 74): regenerated the stale
  favicon from the brand mark (multi-size ico + png + apple-touch, site + admin); fixed the
  store card carousel to show every photo in-card via `card_image_urls` (main + gallery, local
  or remote Printify src, de-duplicated, no N+1) + kept arrows visible on touch; fixed the
  "Refine your look" filters to collapse fully (residual padding-bottom clipped — no sliver);
  made the PDP Color/Size controls premium (gold accent by default, and the variant dropdown
  now renders as a real bordered+shadowed box that isn't clipped — the `1px solid var(--border)`
  double-shorthand and undefined `--shadow-lg` bugs are fixed); and wired discreet per-visitor
  shipping-country detection (CDN `CF-IPCountry`, session-cached, valid per-country rates). No
  migration. See `docs/STORE_VISUAL_INTERACTION_FIXES_2026.md`.
- **Printify sync UX + Glitchy branding + premium loader** (Phase 73): root-caused "connected
  but no products" — our own previous over-aggressive policy hid every product missing
  price/image/category, and the storefront filters hidden ones, so the owner saw created>0 but
  0 visible with only a transient message. Fix: only **unsellable** (no-price) products hide;
  incomplete-but-sellable ones import **visible + flagged**; a **persistent report** (SyncLog
  richer counts + JSON detail) shows created/updated/hidden/skipped + per-product reasons +
  links to the hidden set. `PrintifySyncState` → readonly **"Sync Monitor"** (explained). Admin
  now shows the **Glitchy logo + favicon** (not the settings icon). Premium **loader overlay**
  (stepped, reduced-motion safe) on every Printify operation. Migration `0007`; no publish/order,
  token never leaks. See `docs/PRINTIFY_SYNC_UX_BRANDING_LOADER_2026.md`.
- **Printify admin connection + shop discovery + catalog import** (Phase 72): the admin is now
  operational end-to-end. Root cause of "credentials entered but nothing imported": sync used
  the *env* token (not the admin config), the actions were changelist-only (no change-form
  buttons), and `shop_id` was a free text field holding a shop *name* (`Fabricon`) instead of
  the numeric id. Fix: `shop_id` is button-driven — **Discover shops** (`GET /shops.json`) →
  **Use this shop** saves the numeric id (+ title/channel) → **Test connection** / **Dry-run**
  / **Sync products now** import via the config credentials into the local catalogue only.
  Missing-data products import hidden (to review). Publishing + order creation stay OFF; no
  publish/order endpoint is ever called; token never leaks. Migration `0006`. See
  `docs/PRINTIFY_ADMIN_CONNECTION_SHOP_DISCOVERY_CATALOG_IMPORT_2026.md`.
- **Admin forms premium polish** (Phase 71): fixed the flagged PrintifyAccountConfig add form
  — its custom ModelForm's inputs rendered as bare ~invisible `vTextField` because Unfold only
  styles its own widgets; now every widget gets Unfold's input classes. Added a form CSS
  safety-net (any bare admin input stays visible), a slim add form (auto/readonly fields hidden
  on create), inline-grey checkbox help, a fixed oversized changelist Filters button, disabled
  the broken Order add page (was a 500), and hid the unused `Category.cat_image` field. Token
  never leaks (tested). No migration/dependency. See `docs/ADMIN_FORMS_PREMIUM_POLISH_2026.md`.
- **Ultra-premium admin login** (Phase 70): a split-panel luxury sign-in — espresso/gold brand
  hero with the **animated Glitchy monogram** (cream "G" + tricolore glitch strokes that
  oscillate left↔right, matching the site logo, reduced-motion safe), trust notes and an
  environment badge, beside an elevated form card with refined focus/error states. No token/PII
  in the HTML (test-asserted). No migration/dependency. See `docs/ADMIN_PREMIUM_LOGIN_2026.md`.
- **Ultra-premium admin visual analytics + motion** (Phase 69): the Unfold admin dashboard is
  now a luxury "Commerce Studio" decision panel — a champagne/espresso design system, sober
  motion (reveal, count-up, ring/bar draw, `prefers-reduced-motion` safe, no CLS), and **real
  CSS/SVG charts with NO CDN**: a catalog **health-score ring**, product-status **donuts**,
  **Printify sync-health** (safe defaults badges, never the token), a 7-day orders
  **sparkline**, category-readiness bars and wishlist demand. Fully server-computed (renders
  without JS), aggregate (no N+1), no token/PII. 665 tests green, no migration. See
  `docs/ADMIN_ULTRA_PREMIUM_VISUAL_ANALYTICS_MOTION_2026.md`.
- **Premium Admin + Printify Control Center** (Phase 68-admin): Django **Unfold** admin
  ("Glitchy Commerce Studio") with a real KPI dashboard, thumbnail/filter-rich product admin,
  a `catalog_health_check` command, and premium order badges. Security core: a
  `PrintifyAccountConfig` model that stores the API token **Fernet-encrypted, write-only**
  (never rendered/logged — masked last-4 + fingerprint only), superadmin-gated, with
  admin-controlled sync (test-connection / dry-run) and **all dangerous flags default OFF**.
  New migration (`0005`), new deps (django-unfold, cryptography), new env `PRINTIFY_CONFIG_KEY`.
  655 tests green. See `docs/PREMIUM_ADMIN_PRINTIFY_CONTROL_CENTER_2026.md`.
- **Premium store: recently viewed, compare, safe quick-add** (Phase 67): recently-viewed
  rail on the store (session-based, no PII, one query); lightweight compare (localStorage
  ids only, max 3, drawer/mobile sheet, real data, decimal-validated ids); safe quick-add
  AJAX (`/cart/quick-add/`) that adds simple products and opens Quick View for variant
  products — POST+CSRF, scoped, never creates an order. Fixed owner-reported button design
  (missing FA6 icon → text "Compare", 2-row layout) and a QA-data artifact that made one card
  look broken/smaller. 639 tests green, no migration. See
  `docs/PREMIUM_STORE_RECENTLY_VIEWED_COMPARE_QUICK_ADD_2026.md`.
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
