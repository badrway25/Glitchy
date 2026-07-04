# Glitchy — Ultra-Premium E-commerce UX Polish (2026)

**Branch:** `polish/glitchy-ultra-premium-ecommerce-ux` (from `release/staging-printify-fashion-store
@ 1c2c9b6`). **No migration.** No deploy, no push without authorization, no real payment/order/API
mutation. All shipping/return claims are config-bound or removed.

## 0. Method
A 6-reader parallel audit workflow (656k tokens) mapped the whole storefront first. Key finding:
after ~12 prior premium phases, most of the surface is already genuinely premium (hero+motion,
sticky nav with hover-intent dropdowns + autocomplete search, luxury filters, card carousels,
quick view, wishlist/compare, coupon, PDP gallery/lightbox/sticky-buy, checkout steps, dark mode,
i18n). This phase therefore implemented the audit's **prioritized real gaps** instead of repainting
what already works. The synthesized 12-item plan is preserved in the workflow output; items done
here are listed below, deferred ones in §10.

## 1. Loader G with Italian tricolore (NEW — mandated feature)
Global premium loader: the brand "G" (same geometry as the admin monogram) **draws itself** in a
loop (`pathLength=100` dash animation) beside three tricolore strokes with a staggered
glitch-drift — on a blurred cream/espresso overlay with a spaced "LOADING…" label
(server-rendered, translated). Engineering: hidden at first paint (zero LCP/Lighthouse cost — no
animation runs while `[hidden]`), shows only when a navigation/submit is **actually slow**
(220ms threshold), min-visible 450ms (no flash), 12s watchdog, bfcache-safe (`pageshow` hides),
`data-no-loader` opt-out, `window.glLoader.show/hide` API for AJAX, reduced-motion = static
fully-drawn G, `role=status`. Files: `base.html` (markup), `premium.css` (§loader),
`js/loader-g.js`. No-JS: stays hidden, zero impact.

## 2. Data coherence — shipping/returns/costs (the audit's #1)
- **payments.html** hardcoded **"30-day returns" beside the Pay button** while the real config is
  `RETURN_WINDOW_DAYS=14` → now `{{ d }}-day returns` from config; hardcoded `€` → `CURRENCY_SYMBOL`;
  "Secure payment / Qty / each / Pay" now translated.
- **Deleted `orders/order_recieved_email.html`** — an orphaned template (0 references) carrying the
  invented "Estimated delivery: 2–4 business days".
- **Home hero** hardcoded "free 14-day returns" → config-bound blocktrans.
- **One delivery-ETA model funnel-wide:** the cart/checkout estimator's local fallback discarded
  the rate-table's `min/max days` and showed production+transit (7–27d) while the PDP quote and
  order snapshot show the table (IT 3–6d). Fixed: `_single_option(days_override=…)` uses the table
  days verbatim in Tier-3; decision documented in `settings.py` (table days are door-to-door).
- **Footer** tagline "fast shipping" (unsupported speed claim) → "honest pricing"; newsletter
  heading "…& 10% off" (no configured welcome coupon) → "…& member offers".
- **Guard tests** (`store/test_shipping_copy_guard.py`): (a) forbidden-claim scan over all
  templates (30-day, N–N business days, 24h/48h, IT/FR variants); (b) home trust claims must
  render the config values; (c) estimator fallback days == rate-table days (the funnel-coherence
  invariant).

## 3. Honest merchandising (badges + availability)
- "New" badge fired on `countReview == 0` → old unreviewed products were "New" forever. Now
  `Product.is_new_arrival` with a single site-wide window (`NEW_ARRIVAL_DAYS = 14` in models,
  imported by the store filter — badge and filter can never disagree).
- Sale badge reused the red sold-out class (`badge-out`) → distinct positive `badge-sale`.
- Sold-out cards kept a clickable Add-to-cart that failed after an AJAX round-trip → now a
  disabled "Sold out" CTA (`aria-disabled`).

## 4. PDP add-to-cart: AJAX + toast (conversion)
The primary buy action did a full redirect to /cart (yanking the shopper off the page). Now:
`add_cart` answers **JSON when called via XHR** (same code path, variations included; the
untranslated f-string messages became translated `_()` strings) and `store-features.js` intercepts
`#pdpForm` — respects the variant-guard (defaultPrevented), busy-state on the CTA, success toast
"Added to your bag" + navbar badge pop, `needs_options` → warn toast. No-JS/fetch-failure: the
original POST+redirect still works. **Browser-verified end-to-end** (variants picked → stayed on
PDP → toast → badge 0→1).

## 5. Feedback layer consolidation (toasts)
Two toast systems both styled bare `.toast` — premium.css (glToast, bottom-right, flex) loaded
after theme.css (Django messages, top-right, grid) and corrupted the message-toast layout; message
toasts were hardcoded white in dark mode. Fixed: both trees **scoped** (`.toast-wrap .toast` /
`.toast-host .toast`), dark-mode surface added, and the **6 double-render `alerts.html` includes
removed** (login/register/dashboard/forgot/reset/PDP-reviews rendered every message twice —
inline alert + toast); `includes/alerts.html` deleted.

## 6. FA icons (feedback moments rendered empty)
The site ships Font Awesome 5.8.2 but 10 files used FA6-only names (toast icons, order-complete,
my-orders, billing, transactions, PDP info, wishlist, address list, portal filters, store) →
mapped to FA5 (`fa-check-circle`, `fa-info-circle`, `fa-exclamation-triangle`, `fa-times`,
`fa-shopping-bag`, `fa-search`). New guard: `store/test_icon_guard.py` scans templates+JS for
FA6-only names (already caught 4 extra files during this phase).

## 7. Mobile conversion + a11y
- **Persistent cart/wishlist icons in the mobile header** (with live badges) — before, the entire
  actions block was buried inside the hamburger drawer (cart count invisible without opening it).
- Drawer accessibility completed: `role=dialog` + `aria-modal`, **aria-expanded synced** on the
  toggler (was stuck "false" forever), focus trap (Tab loop), focus-restore on close, Esc only
  when open, close-label/adding-label now server-translated via body data attributes.
- **Skip-to-content link** + focusable `#main-content` wrapper in base.html (div target — several
  pages already use `<main>` internally, avoiding invalid nesting).
- Store **pagination now preserves every active filter** (was silently dropping them all), uses
  Django's elided page range, `aria-label` prev/next + `aria-current="page"`.

## 8. Footer honesty + newsletter UX
- 7 dead `href="#"` links removed: About/Sustainability/Press → real Collections/Privacy/Terms;
  social buttons now render **only when configured** (`SOCIAL_INSTAGRAM/TIKTOK/YOUTUBE/FACEBOOK`
  env → `SOCIAL_LINKS` context processor); "Shipping" no longer duplicates Returns (→ FAQ).
- Newsletter: the existing JSON endpoint is finally used — AJAX submit, button morphs to
  "You're in ✓", duplicate-email info toast, no more full-page reload; no-JS unchanged.

## 9. SEO (real data only)
- PDP now overrides `meta_description`, `og:title`, `og:description`, `og:image` with the real
  product name/description/cover (was: generic tagline + default og-image on every product).
- Product JSON-LD enriched with real fields only: `sku` (slug), `brand`, `offers.url`,
  `hasMerchantReturnPolicy` from `RETURN_WINDOW_DAYS`. AggregateRating stays conditional on real
  reviews. No invented priceValidUntil/ratings.
- `WebSite` + `SearchAction` JSON-LD in base.html (the search endpoint is real).

## 10. Deferred (honest — from the audit's plan)
- **Return window anchored to order date** (`returns/services.py`) while copy says "from delivery"
  — a real business-logic fix (P2) needing an order-delivery timestamp design; NOT done here.
- **Checkout validation re-render** (P10): invalid `place_order` still redirects and loses typed
  fields; needs bound-form re-render + inline errors.
- **Full i18n sweep of the money path** (P11): PDP reviews block + several `carts/orders/accounts`
  Python messages remain English (a few were translated opportunistically here).
- Homepage card feature-parity with store cards; mini-cart drawer (toast-action chosen instead).

## 11. Verification
- **Tests:** full suite green (see report), + 2 new guard files (shipping-copy 3, icon 1).
- **Gate:** check ✓ · makemigrations --check "No changes" ✓ · collectstatic ✓ · staging_check
  0 failures ✓.
- **Browser QA** (console 0, HTTP 500 0, horizontal overflow 0 at 390/1440): loader G animation,
  PDP AJAX flow, mobile header icons + drawer aria/Esc, badges, footer, forms, shipping copy.
  Screenshots in `docs/qa/glitchy_ultra_premium_ecommerce_ux/`.

## 12. Deploy notes
No migration. `collectstatic` + `compilemessages -l it -l fr` + restart. New optional env:
`SOCIAL_INSTAGRAM/SOCIAL_TIKTOK/SOCIAL_YOUTUBE/SOCIAL_FACEBOOK` (empty = buttons hidden).
