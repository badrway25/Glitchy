# Store Card Carousel Functional Fix + Premium Filter Refinement (Phase 75, 2026)

**Branch:** `fix/store-card-carousel-and-premium-filter-system` (from
`release/staging-printify-fashion-store` @ `432bc64`). **No migration.** No deploy. No secrets.

Every fix was verified in the browser with **before/after screenshots** — the carousel image
actually changes, the price focus wraps the €, filters collapse clean and colours select clearly.

## 1. Carousel — the image never changed (real root cause)
Previous phases moved the track (scrollLeft/transform advanced, dots updated) but the **visible
image stayed the same**. Two stacked causes, both found only by a screenshot diff:
1. **`.media-skeleton img{position:absolute; inset:0}`** (theme.css, the aspect-ratio fill
   pattern) also applied to the carousel slide images. Absolutely-positioned images ignore the
   flex track — **all slides stacked at the same spot**, so scrolling/translating the track
   never changed what you saw.
2. **The main product image is a content-duplicate of a gallery image**, and `card_image_urls`
   prepended it — so slides 0 and 1 were the *same photo*; the first "next" looked like a no-op.

**Fix:**
- `.pcard-slide img{position:static!important; inset:auto!important}` — the slide images now
  flow in the flex track, so moving the track moves the image.
- Rewrote `product-card-gallery.js` to a **transform-based** carousel (`translateX(-i*100%)` by
  active index) — deterministic across browsers/devices (no scroll-snap "snap back"), idempotent
  `initProductCardGalleries()`, prev/next + keyboard + **pointer swipe** (a swipe moves the
  carousel; a tap still opens the PDP), arrows hidden at bounds, dots reflect the real index.
- `.pcard-track` is now a transitioned flex track; `.pcard-gallery{overflow:hidden}` clips it.
- `card_image_urls` sources the **gallery first** (the distinct mockups); the main image is only
  a fallback when there's no gallery — so consecutive slides are different photos.
- Verified: click next → NEW DAY front print → folded plain shirt (distinct images render);
  prev returns; single-image cards show no controls.

## 2. Price filter — focus didn't include the € symbol
The `<label class="lxf-price-field">` wraps `.lxf-cur` (€) + a borderless `<input>`, with
`:focus-within` styling. It works, but needed the input's own outline suppressed and the field
padding tuned so the gold focus ring wraps the **whole group** (€ + value). Verified: focusing
the input shows a single gold ring around "€ 16".

## 3. Filter collapse/expand — inputs cramped against the header
The expanded body only had `padding-bottom` (no top), so re-opening a group put the inputs flush
under the title. **Fix:** `.lxf-body > *{padding:.9rem .1rem 1rem}` (top breathing room),
`.is-collapsed .lxf-body > *{padding-top:0;padding-bottom:0}` so collapsed stays truly 0 height
(still clipped by the container `overflow:hidden`). Applies to every group.

## 4. Colour filter — selection unclear
The swatch already toggled a gold ring, but it read as subtle. **Fix:** the selected row now has
a **champagne background wash + a gold ✓ checkmark + a stronger ring/scale + bold label**, plus
the group header shows an active-count badge. Verified: `?color=black` → Black row highlighted
with ✓, results filtered (5). Unknown colours fall back to a neutral dot + text label.

## 5. Other filters
Category (active item filled), Size (filled pill when selected), Rating (filled "Any"),
Availability (toggles) already have clear premium selected states; all now share the corrected
header spacing. `SHOW RESULTS · N` and `CLEAR ALL` unchanged.

## 6. Motion / a11y / performance
Carousel + collapse are `prefers-reduced-motion` safe (transition disabled). Keyboard: arrows on
the focusable track, focus-visible rings on inputs/swatches, `aria-expanded` on group headers.
No N+1 (`card_image_urls` uses the prefetched gallery). No CLS (fixed slide sizing, grid-row
collapse). Prev/next are `<button type="button">` with `preventDefault`+`stopPropagation` so they
never navigate to the PDP; quick-view / wishlist / compare / quick-add untouched.

## 7. Tests
`store/test_carousel_filters.py` (10): gallery-first ordering (main not prepended), URL dedupe,
carousel JS is transform-based + idempotent, slide img forced static + gallery overflow hidden,
next control is `type=button`, price `:focus-within`, filter body top-spacing + collapsed-zero,
colour selected state (bg + ✓), colour querystring applies. Plus the Phase-74 store tests.

## 8. QA (browser, real interactions, console 0, overflow 0)
`/store/` at 390/1280, light + dark: carousel next/prev changes the image (screenshot-verified),
price focus wraps the €, every group collapses to nothing and re-opens with spacing, colour
selection is obvious and filters results, mobile drawer opens without overflow. 8 screenshots in
`docs/qa/store_filter_carousel_final_fix/`.

## 9. Limits
- Content-duplicate images *within* the gallery aren't de-duped (URL dedupe only); Printify
  mockups are normally distinct, and the main-vs-gallery duplicate (the actual bug) is fixed.
- Size pills use the primary (espresso) fill when selected rather than gold — consistent with
  the existing pill system; can be gold-tinted later if desired.
