# Store Visual Interaction Fixes + Glitchy Favicon (Phase 74, 2026)

**Branch:** `fix/store-carousel-filters-product-options-favicon` (from
`release/staging-printify-fashion-store` @ `30a6470`). **No migration.** No deploy. No secrets.

Owner-reported, verified live-style in the browser (not just green tests).

## 1. Favicon was still the old one
`greatkart/static/images/favicon.ico` was the stale 16×16, ~1.1 KB icon from the original
theme — not Glitchy. **Fix:** regenerated the favicon from the brand mark
(`logo-glitchy-mark.png`) with Pillow into a multi-size `favicon.ico` (16/32/48, ~5.8 KB) plus
`favicon-32.png`, `favicon-16.png` and an `apple-touch-icon.png` (180×180 on the espresso brand
bg). Wired in `templates/base.html` (`rel=icon` ico + png + apple-touch + `theme-color`). The
admin favicon already points to the same asset via `UNFOLD["SITE_FAVICONS"]` (Phase 73), so it
updates too. `{% static %}` uses hashed filenames in production → the browser cache busts
automatically. (Gotcha fixed en route: a multi-line `{# … {% static %} … #}` comment — Django
`{# #}` is single-line only, so the literal `{% static %}` inside got parsed as an arg-less tag
and 500'd; switched to `{% comment %}`.)

## 2. Store card carousel didn't preview other photos
Root causes (the JS itself works — a real arrow click advances to a *distinct* image):
- the card built slides from `product.gallery.all` only, and used the gallery's **local file**;
  a synced Printify product whose images failed to download (or whose list payload repeats the
  same mockup URL) showed **one blank/duplicate image** → "must open the detail".
- the prev/next arrows were `opacity:0` until `.product-card:hover` → **invisible on touch
  devices** (no hover).
**Fix:** new `Product.card_image_urls()` — main image first, then gallery images, each resolved
to its **local file OR the remote Printify src**, **de-duplicated**, capped at 5 (uses the
already-prefetched gallery — no N+1). The card renders a carousel whenever there are ≥2
*distinct* images, so synced products show every photo in the card. Arrows are now kept visible
on touch devices (`@media (hover:none)`). `cover_image`/`hover_image` also fall back to the
remote src (single-image synced products no longer show the placeholder).

## 3. "Refine your look" filters left a sliver when collapsed
The groups collapse with `grid-template-rows:1fr→0fr`, but `.lxf-body > *{padding-bottom:1rem}`
— that residual padding overflowed the 0-height track and **wasn't clipped** (~1rem sliver).
**Fix:** `overflow:hidden` on the `.lxf-body` grid container (clips the padding when collapsed)
plus `padding-bottom:0` on the child once `.is-collapsed`. Collapsed height is now exactly 0
(measured) for every group, desktop + mobile drawer, transition still smooth, reduced-motion
safe, `aria-expanded` toggles.

## 4. Product-detail Color/Size options weren't premium & the dropdown box was invisible
Root causes:
- `.custom-select-dd .dropdown-menu` used `border:1px solid var(--border)` — but `--border` is
  already a full shorthand (`1px solid <color>`), so the value was the invalid
  `1px solid 1px solid <color>` → **no border**; and `box-shadow:var(--shadow-lg)` referenced an
  **undefined** token → **no shadow**. The open menu was a borderless, shadowless white
  rectangle on a cream page ("box not visible").
- `.pdp-card` has `overflow:hidden` (theme.css, for the 22px radius) which **clipped** the taller
  Size dropdown.
- the Color/Size buttons were plain white.
**Fix:** menu now uses `border:var(--border-strong)` + `box-shadow:var(--shadow)` (+ scroll
`max-height` for long lists) → a proper elevated box; `.pdp-card{overflow:visible}` with the
media rounded on its own element so dropdowns escape; and the buttons carry the **gold accent by
default** (gold border + soft champagne tint — the hover look moved onto the resting state per
the owner's "invert"), deeper on hover, with gold item hover/selected states. Dark-mode aware,
focus-visible ring, reduced-motion safe.

## 5. Shipping line now reflects the visitor's country (discreetly)
The PDP trust line ("Ships to … · shipping · ETA · returns") was already dynamic
(`ship_country_name` + `shipping_quote` with a real per-country rate table: IT/FR/DE/ES/GB/US +
default). It showed Italy because nothing resolved a country. **Fix:** `detect_country` now
caches the auto-detected country in the session (one-time, stable per visitor) and prefers the
**CDN/proxy country header** (`CF-IPCountry` etc.) — server-side, **no external call, no PII**.
On production behind Cloudflare this auto-detects; an explicit country switcher still wins, and
an opt-in cached IP lookup (`SHIPPING_GEOIP_API`) is the last resort. Verified: FR → €6.90 /
4–8 days, US → €9.90 / 6–12 days, IT → €4.90 / 3–6 days.

## 6. Tests
`store/test_visual_interaction.py` (11): card_image_urls remote-src fallback + dedupe +
single-vs-multi, cover_image fallback, store card renders the carousel, base template links the
Glitchy favicon + theme-color, favicon regenerated multi-size (+ png/apple-touch present),
CDN-header country detection + session cache, manual override wins, default fallback, valid
per-country quotes.

## 7. QA (browser, real interactions)
`/store/` (light + dark + 390 mobile, overflow 0, console 0): carousel arrow advances to a
distinct image (`_duM6LZi` → `_RkUsHEW`) without navigating; every filter group collapses to 0
height (no sliver) and re-expands; PDP Color/Size buttons are gold-accented and the variant
dropdown opens as a bordered, shadowed box that isn't clipped (7 items). 7 screenshots in
`docs/qa/store_visual_interaction_fixes/`.

## 8. Limits / honest notes
- The carousel + dropdown fixes are verified locally; the owner sees them "still broken" on
  glitchy.graphics only because this branch isn't deployed yet.
- Country auto-detection needs a CDN country header (automatic on Cloudflare) or the opt-in IP
  lookup; without either it falls back to the default (IT). No external call is made by default.
- `card_image_urls` caps at 5 images (matches the previous card behaviour).
