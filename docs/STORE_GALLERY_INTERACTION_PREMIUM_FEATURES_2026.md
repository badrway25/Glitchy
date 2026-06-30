# Store Product Gallery Interaction Fix + Premium Features (Phase 66, 2026)

**Branch:** `fix/store-card-gallery-interaction-premium-features` (from
`release/staging-printify-fashion-store` @ `1460135`). **No DB migration.** No real
orders/payments; Printify push/sync OFF.

## 1. Bug reported
On the store, clicking the arrow / swiping right to see a product's other photos did
nothing — the product-card gallery (Phase 61) was not actually usable.

## 2. Root cause (verified in the browser, not assumed)
The carousel track (`.pcard-track`) is `overflow-x:auto; scroll-snap-type:x mandatory` and
each slide is full-width (`flex:0 0 100%`). The slides used **`scroll-snap-align: center`**.
With full-bleed slides + `mandatory` snapping, `center` alignment **pins `scrollLeft` to 0** —
the track refuses to hold any other position, so both swipe and arrow-scroll snap straight
back to the first image.

Empirical proof (browser DOM probe on `/store/`):
- `scrollWidth 1540 > clientWidth 308` (content overflows, *should* scroll), yet setting
  `scrollLeft` to 100 / 308 always read back **0** with the original CSS.
- Temporarily setting `scroll-snap-type:none` → `scrollLeft=308` held. Setting
  `scroll-snap-align:start` → `scrollLeft=308` held. → the **alignment** was the culprit.

## 3. The fix
`.pcard-slide { scroll-snap-align: start; scroll-snap-stop: always; }` (was `center`), plus
`.pcard-track { touch-action: pan-x pinch-zoom; }` for crisp horizontal touch panning. One
CSS change; the existing JS (`product-card-gallery.js`) was already correct.

Post-fix verification (browser, `/store/`):
- Clicking **next** advances slide-by-slide: `scrollLeft 0 → 308 → 616 → 924`; **prev**
  returns to 616. Dots update; **no navigation to the PDP**.
- Intermediate positions snap to the nearest slide (`460 → 308`, `900 → 924`) — correct
  carousel behaviour.
- Mobile 390: `clientWidth 156`, scroll holds at slide 2 (156) — swipe works.
- A **CSS regression-guard test** asserts `.pcard-slide` uses `start` and never `center`.

## 4. How the gallery works
Multi-image products (≤ 5 images) render a horizontal scroll-snap track of `<a>` slides
(each links to the PDP), discreet prev/next buttons (revealed on hover / focus; always
slightly visible on touch via `@media (hover:none)`), and dots. The JS scrolls one slide on
arrow click (`preventDefault + stopPropagation` so the arrow never opens the PDP), updates
dots on scroll (rAF-throttled), handles ←/→ when the track is focused, and respects
`prefers-reduced-motion`. Single-image products render a plain image with **no controls**.
Tapping an image opens the PDP; a horizontal swipe scrolls (native), it does not navigate.

## 5. Premium features added (real, data-driven)
- **Colour + size swatches on cards** — distinct active `Variation` colours (rendered as
  hex dots via the existing `color_hex` filter) and size pills, max 4 + “+N”. Built on a new
  `Product.card_variants()` that reads the **prefetched** `variation_set` (the store view now
  `prefetch_related("gallery","variation_set")`) → **no N+1** (test-asserted: 0 extra queries
  iterating all cards). Shows nothing when a product has no variants.
- **Trust / delivery micro-panel** — an honest strip above the grid: *Made on demand ·
  Delivery estimate before you pay · Secure checkout · Receipts in your account*. No false
  claims (no "free shipping", no guaranteed times). EN/IT/FR.

## 6. Features evaluated but deliberately deferred (honest)
- **Smart quick-add** (FASE 5): the card already has a **Quick view** button that opens the
  drawer where size/colour are chosen before adding — the safe path. A direct
  add-to-cart-for-simple-products variant is a low-risk follow-up; not adding it avoids any
  chance of adding a wrong/missing variant.
- **Recently-viewed rail** (FASE 6) and **compare** (FASE 7): deferred to keep this branch a
  focused, well-verified gallery fix + two solid features rather than several half-built ones.

## 7. Accessibility
Arrows are real `<button>`s with `aria-label` (Previous/Next image); dots are
`aria-hidden`; the track is a labelled focusable `role=group` with ←/→ keys; swatches carry
an `aria-label`; reduced-motion respected; touch targets preserved.

## 8. Performance
Store cards prefetch gallery **and** variations (one query each, not per-card). No new
per-card queries (`card_variants()` reads prefetched data). No CLS. Images stay lazy
(first eager). One small CSS change + no new JS.

## 9. i18n
New strings (trust panel, "Available options") in EN/IT/FR, compiled.

## 10. QA
Local `127.0.0.1`, **375/390/1280/1440**, light + dark, EN, **console 0**. Gallery
interaction verified empirically (arrow scroll sequence, mobile swipe hold, no accidental
navigation). 9 PII-safe screenshots in `docs/qa/phase66/`.

## 11. Limits
- Recently-viewed / compare / direct simple-add not implemented (see §6).
- Swatches show only products that actually have colour/size variants (the demo catalogue
  has them on the Printify items).
