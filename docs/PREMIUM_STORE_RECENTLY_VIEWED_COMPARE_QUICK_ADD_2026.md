# Premium Store: Recently Viewed, Compare, Quick Add (Phase 67, 2026)

**Branch:** `feature/store-premium-recently-viewed-compare-quick-add` (from
`release/staging-printify-fashion-store` @ `ec0a707`). **No DB migration.** No real
orders/payments; Printify push/sync OFF.

## 1. Features added
1. **Recently viewed rail** — an elegant horizontal rail (scroll-snap, `snap-align:start`)
   on the store, built on the **existing privacy-safe session mechanism**
   (`storefront/recently.py`) rather than localStorage: it stores only product ids
   server-side (no PII), is one query (no N+1), excludes nothing on the store, and is hidden
   when empty. The PDP already had the same data. *(Design note: the session approach
   achieves the brief's "no PII" goal more robustly than localStorage and was already
   proven.)*
2. **Lightweight compare** — a "Compare" toggle on each card adds the product id to
   **localStorage** (`gl_compare`, **ids only, no PII**, max 3). A floating bar shows the
   count and opens a **drawer** (full-screen sheet on mobile) that fetches `/store/compare/`
   and shows image, name, price (+ sale), category, colours, sizes side by side, with
   remove / clear all and View details / Choose options CTAs. Server validates ids
   (decimal-only, capped at 3, available products only) and autoescapes output.
3. **Safe quick add** — simple products (no required size/colour) get an **"Add to cart"**
   that POSTs to a new `/cart/quick-add/<id>/` AJAX endpoint and updates the cart badge +
   shows a toast. Products that need a variation get **"Choose options"** which opens Quick
   View — a wrong variation is never added. The endpoint is `@require_POST`, CSRF-protected,
   ownership/session-scoped, refuses unavailable products (409), and **never creates an
   order or takes payment**.
4. **Toast feedback** — reused across add-to-cart, compare add/remove, wishlist (Phase 65).
   `aria-live`, reduced-motion safe.

## 2. Safety / security
- `quick_add` only writes `CartItem`; it cannot create an `Order` or call any payment
  path. POST + CSRF enforced; cart scoped to the user (auth) or session (guest). Tests
  prove: simple adds, variant returns `needs_options` (adds nothing), never creates an
  order, increments not duplicates, POST-only.
- `compare` ids are **decimal-validated** (`isdecimal()`, not `isdigit()` — the latter
  accepts e.g. "²" which crashes `int()`; a review caught this), capped at 3, scoped to
  available products; output autoescaped (no XSS). Garbage/Unicode/`<script>` ids are safe
  (tested).
- **localStorage holds only product ids** (`gl_compare`) — no PII.

## 3. Bug fixes this session (owner feedback)
- **Card slides "not working" + first card smaller**: caused by a QA test product (a
  single-image, no-variant item) that I had added to the dev catalogue — it showed no
  carousel (single image) and was shorter (no swatches), which read as "broken". Removed it;
  the real catalogue is uniform and the Phase 66 gallery works (verified: next click scrolls
  `0→308→616`, no accidental navigation). Added a flex equal-height safeguard so any future
  no-swatch product still aligns.
- **Ugly compare button**: the icon was `fa-scale-balanced` (FontAwesome 6) which is not in
  the loaded build → an empty box; and the 3-buttons-in-a-row clipped "Choose options".
  Fixed: a clean **two-row layout** (full-width primary CTA, then View + a text **"Compare"**
  button), no missing-icon dependency, no clipping, uniform heights.

## 4. Performance
Store view now `prefetch_related("gallery", "variation_set")` — gallery, swatches and
compare all read prefetched data (no N+1, test-asserted). Recently-viewed is one query.
Compare fetch is a single id-scoped query. One small vanilla JS file.

## 5. Accessibility
Compare bar/drawer are dialog-roled with aria-labels and Escape-to-close; toggle buttons use
`aria-pressed`; toasts are `aria-live`; the recently-viewed rail is keyboard-scrollable;
reduced-motion respected.

## 6. i18n
New strings (compare, recently viewed, quick add, choose options) in EN/IT/FR, compiled.

## 7. QA
Local `127.0.0.1`, **375/390/1280/1440**, light + dark, **console 0**, **0 overflow**.
Verified in-browser: quick-add (cart 0→1 + toast, no reload, no order), compare
(toggle→bar→drawer, localStorage `["10","7"]` ids only), recently-viewed rail (4 cards),
gallery still scrolls. 11 PII-safe screenshots in `docs/qa/phase67/`.

## 8. Limits (honest)
- Recently-viewed uses the **session** mechanism (privacy-safe, server-rendered) rather than
  a localStorage reimplementation — same privacy goal, more robust.
- The current demo catalogue products all have variants, so the live "Add to cart" path only
  appears for simple products (the feature is fully tested; a simple QA product demonstrated
  it before removal).
- Quick View was reused as the "choose options" path (already supports variant selection +
  add); a deeper Quick-View redesign was out of scope.
