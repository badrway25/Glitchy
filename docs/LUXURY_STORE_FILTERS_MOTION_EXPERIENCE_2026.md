# Luxury store filters, motion & editorial experience (2026)

**Branch:** `feature/luxury-store-filters-motion-experience` (from
`feature/ultra-premium-filters-categories-checkout-cro` @ `30e6c7b`).
A deep, **visible** redesign of the `/store` left filter rail, the mobile filter
experience, scroll/collapse motion, and category heroes. **No DB migration.**
No real orders/payments; Stripe TEST; Printify push OFF; `SHIPPING_USE_PRINTIFY`
off at rest.

---

## 1. What wasn't premium enough (honest)
The previous filter rail was a flat stack of native checkboxes / chips with a
plain "Filters" header. Colours were text labels, sizes were square checkboxes,
sections didn't collapse, the mobile drawer was a side panel without a sticky
action footer, and the store had **no motion** at all. Category pages had no
editorial hero. That read "functional", not "luxury".

## 2. Filter sidebar — Luxury 2.0 (redesigned)
- Editorial header **"Refine your look / Affina il tuo stile / Affinez votre
  style"** + microcopy + sliders icon.
- Every section is a real **collapsible** (`<button aria-expanded aria-controls>` +
  region) with a chevron and a **smooth `grid-template-rows` animation**; open/closed
  state is **persisted in localStorage** (`gk_filter_collapsed`).
- **Per-section active-count badges** (JS counts checked inputs / set price).
- Thin dividers, refined spacing, sticky on desktop (inherited), dark-mode perfect.
- Footer CTA **"Show results · N"** + refined **"Clear all"**.

## 3. Colour / size / price / rating / availability
- **Colour:** circular **swatches** with a safe name→hex map (`color_hex`
  template filter; neutral fallback for unknowns, visible ring for light tones),
  product count, **gold selected ring**, keyboard-focusable, tooltip label.
- **Size:** fashion **pills** (native checkbox visually hidden, label styled),
  dark selected state, hover accent border, focus ring.
- **Rating:** pills (`4★+ … Any`).
- **Availability:** real **toggle switches** (In stock / On sale / New arrivals)
  with live counts — only real facet data, no invented stock.
- **Price:** premium framed inputs with currency prefix and focus ring (no heavy
  slider dependency — kept fast and robust; min/max remain shareable GET params).

## 4. Mobile filter — bottom sheet
Side drawer → **bottom sheet**: rounded top, **drag handle**, body scroll,
**sticky footer** (Clear · Show results · N), backdrop, **scroll lock**, Esc /
click-outside, **focus trap + restore focus** to the opener. Verified 375/390.

## 5. Motion (JS, progressive, accessible)
`store-luxury.js` (vanilla, no deps): scroll **reveal** for product/category
cards via **IntersectionObserver** (with a 1.4 s failsafe), smooth section
collapse, selected-state transitions. Card hover elevation + image micro-zoom are
CSS. **Everything is gated on `prefers-reduced-motion`** and degrades to a fully
working no-JS store (sections render open, cards visible).

## 6. Category / collections
- **Category editorial hero**: eyebrow, title, description (or a localized
  fallback), and meta chips (count · Made on demand · Ships worldwide). Shown only
  on category pages; the technical **"Printify" category stays 404**.
- Collections page kept (cards already editorial); not re-templated this phase
  (honest — see Limits).

## 7. Smart features (2, robust)
1. **"Continue your search"** — the last applied filter URL is saved to
   localStorage (`gk_saved_filters`); a clean `/store` shows a **Resume / Dismiss**
   banner. Pure enhancement, dismissable, no PII.
2. **Smart empty state** — zero-result view already offered clear-filters +
   recommendations; now also shows **real category** suggestion chips + a
   "Showing N styles" lead on the active-chips bar.

## 8. Checkout / forms
Inherited the Phase 55 step indicator + sticky summary + shipping estimator
(no nested form, no accidental submit — still covered). This phase focused on the
store; checkout got microcopy/consistency only (see Limits).

## 9. Accessibility
Collapsibles: `aria-expanded`/`aria-controls`, focus-visible rings. Swatches/pills/
toggles keep the native input (keyboard + screen-reader) while restyling the label.
Mobile sheet: `role=dialog aria-modal`, focus trap + restore. Quick View focus
trap (Phase 55) intact. Reduced-motion honored everywhere.

## 10. Performance / JS quality
One small vanilla file, event listeners scoped, `IntersectionObserver` unobserves
on reveal, localStorage payloads tiny, no new dependency, no layout thrashing, no
duplicate listeners. CSS uses modern `:has()` for selected states (graceful).

## 11. QA
`127.0.0.1:8799`, viewports 375/390/1280/1440, EN/IT/FR, light+dark. Console
**0 errors**, **0 overflow**, no hover-yellow, no customer-facing Printify
category, no internal cost/ID leak, no real order/payment. 14 screenshots in
`docs/qa/phase56/`. Suite **482 OK**.

## 12. Limits (honest)
- **Price slider** not implemented (kept premium inputs) — deliberate, to avoid a
  heavy dependency / drag-accuracy issues on mobile.
- **Collections** page not re-templated (already decent); category hero is new,
  collections hero is not.
- **Checkout forms** got only light consistency work this phase (the store was the
  focus); floating-labels / address autocomplete still TODO.
- `:has()` selected styling needs a modern browser; the native control still works
  everywhere, so it degrades safely.
- Still **dev/local only** — no public-URL QA; production blockers unchanged
  (staging host, key rotation, live shipping, real catalog).
