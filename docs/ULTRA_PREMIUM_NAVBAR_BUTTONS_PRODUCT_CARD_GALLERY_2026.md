# Ultra-premium navbar buttons + product card image gallery (2026)

**Branch:** `feature/ultra-premium-navbar-buttons-product-card-gallery` (from
`release/staging-printify-fashion-store` @ `5924fbf`). **No DB migration.** No real
orders/payments; Printify push/sync OFF.

## 1. Problem
The navbar `Login`/`Register` buttons were different sizes (outline vs black, .8 vs
.82rem) and Register was espresso-black, not gold. Some global buttons looked
Bootstrap-ish (radius conflict, missing states). And in the store, multi-image
products only showed one image — you had to open the PDP to see the rest.

## 2. Navbar Login / Register
- Both now use a shared `.btn-auth` class → **identical height (42px), padding,
  radius, font-weight, baseline**. Equal visual weight.
- **Register = premium gold** (`.btn-auth-gold`, a sober `--btn-elegant → --accent-2`
  gradient, white text, subtle shadow — not yellow). Hover lifts + brightens.
- **Login = elegant soft** (`.btn-auth-soft`, surface + strong border, gold border on
  hover, subtle lift). Reads premium, not a poor secondary.
- Dark mode variants for both; `:focus-visible` rings; `:active` press.
- Mobile: the pair lives in the nav drawer (equal-size, gold Register, tappable).

## 3. Button & icon system (global, additive)
- Unified `border-radius:var(--radius-sm)` on the main variants (fixing a theme.css
  14px vs 6px conflict).
- Added missing states across `.btn`: `:disabled` (dimmed, not-allowed),
  `:active` (press), `:focus-visible` (gold ring), and an opt-in `.is-loading`
  spinner. `.btn-icontext/.btn-with-icon` use inline-flex for perfect icon/text
  alignment; `.btn i/.ic` vertically centered.
- Subtle icon micro-motion (nav icon lift, arrow/chevron glide) — all
  `prefers-reduced-motion` safe. Mobile product-action buttons get a 44px tap target.

## 4. Product card image carousel (the feature)
- A multi-image product now renders a **scroll-snap carousel right in the store
  card** — no need to open the PDP. Built on the existing `ProductImage` gallery
  (already `prefetch_related("gallery")` in the store view → **no N+1**).
- **Desktop:** discreet circular prev/next arrows reveal on hover/focus; end-arrows
  hide at the bounds; clicking an image still goes to the PDP.
- **Mobile:** native horizontal **swipe** with CSS `scroll-snap` + small dots.
- **Keyboard:** the track is focusable; ←/→ scroll. Dots reflect position (decorative,
  `aria-hidden`); arrows are aria-labelled.
- **Performance / no CLS:** fixed 4:3 media box (unchanged), first image `eager`, the
  rest `lazy`+`decoding=async`, `width/height` set. Capped at **5 images** per card.
- **Fallback:** a product with **one (or zero) image** keeps the exact current
  single-image card (cover + hover, placeholder if missing) — **no controls**.
- Implemented with a tiny vanilla `product-card-gallery.js` (no library), safe when
  no carousel exists; light/dark; reduced-motion (instant scroll).

## 5. Accessibility
Equal-size buttons with visible focus; gold Register has sufficient contrast (white
on the deep-gold gradient / dark text in dark mode); carousel images carry alt text,
the track is a labelled focusable group, arrows are aria-labelled, dots are
decorative; reduced-motion respected throughout.

## 6. i18n
New strings (Previous/Next image, "{name} — product images") in EN/IT/FR, compiled.

## 7. QA
Local `127.0.0.1`, 375/390/1280/1440, EN/IT/FR, light + dark. Console **0**,
**0** overflow, no layout shift. Carousel verified: scroll (0→one slide), dots
update, prev hides at start, single-image fallback, 5-image cap, mobile swipe
(scrollWidth 740 > 148, snaps). Checkout redirect (Phase 60), language switcher
(Phase 57), quick view, wishlist, filters all intact. Screenshots in
`docs/qa/phase61/`.

## 8. Limits (honest)
- Desktop "drag to swipe" is not enabled (clicking an image opens the PDP, by
  design); desktop uses the arrows, mobile uses native touch swipe.
- The button-system pass is **additive/surgical** (states, alignment, radius unify,
  navbar auth) rather than a full re-architecture into a new `.btn-premium-*` family —
  to avoid regressing the 540+ existing tests and many tuned buttons. The new family
  can be introduced incrementally later.
- The carousel shows up to 5 images; the full gallery remains on the PDP.
