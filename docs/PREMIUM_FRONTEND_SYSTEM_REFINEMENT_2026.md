# Premium frontend system refinement (2026)

A focused, regression-safe pass that makes the storefront read more premium, driven
by an automated 5-dimension audit (40 findings). EN/IT/FR, light + dark, mobile
375/390 verified. This is a **first slice** — the broader sweep is tracked under
"Partial / next" below.

## 1. Container & layout width
- New token **`--container-max:1320px`** (+ `--container-narrow:820px`). The 15
  scattered inline `style="max-width:1280px"` container overrides were **centralized**
  to the token (one-line future changes) and widened 1280 → 1320.
- The **footer** container was capped to `--container-max` so it matches the navbar
  (it previously inherited Bootstrap's ~1500px → navbar/footer asymmetry). The
  navbar header container also uses the token. No horizontal overflow at any width.

## 2. Typography — premium serif display
- New display font **Fraunces** (variable, fashion-grade serif, full Latin accents)
  for headings via `--font-display`; **Inter** stays for body/UI (`--font-ui`).
  Graceful fallback stack (`Plus Jakarta Sans`, `Inter`, `Georgia`) while the webfont
  loads (`display=swap`). `font-optical-sizing:auto` + tuned tracking on headings.

## 3. Palette — softer, warmer
- `--primary-2` `#000000` → **`#2a2824`** (no more pure black).
- `--muted` `#7a7368` → **`#6b5f54`** (deeper taupe, better contrast/legibility).
- Gold (`--accent`) stays the single elegant accent. Dark mode unchanged where it
  was already refined (avoided risky broad dark retokenization).

## 4. Search input + button (the owner's specific complaint)
Rebuilt the navbar/store search as a clean **split pill**: one continuous bordered
pill, a **full-height integrated button flush to the right** with matching pill
radius (`border-radius:0 var(--radius-pill) var(--radius-pill) 0`) — **no gap, no
double border, no radius defect**. Input + button heights unified (46px). Added
`:focus-within` so the button highlights with the field; dark-mode keeps a legible
button (existing `.search-go` dark color override). Mobile full-width.

## 5. Buttons & forms
- Unified `:focus-visible` ring across the button family
  (`.btn-soft/.btn-outline-primary/.btn-elegant/.sortx-btn/.btn-icontext`).
- Consistent form-field focus (accent border + focus ring) and smooth transition,
  scoped to `form` so it doesn't touch unrelated controls. No nested `<form>`.

## 6. New section — "How Glitchy works"
A 3-step editorial band on the homepage (EN/IT/FR): **Choose your style → Printed on
demand → Delivered with an estimate**, each with a gold step number, icon tile,
serif title and honest copy (no false claims; mirrors the real pre-checkout delivery
estimate). Scroll-reveal + reduced-motion safe; dark + mobile (stacks to 1 column).

## 7. Text dynamism — hero rotating tagline
A subtle gold-italic **rotating tagline** under the hero sub cycles three brand lines
("Premium tees. Printed on demand. Delivered transparently." / "Your style, estimated
before checkout." / "Designed to feel refined. Built to be transparent."). All lines
are absolutely stacked in a reserved-height box (no layout jump); reduced-motion (CSS
and JS, incl. mid-session toggle) shows the first line only.

## QA
Local `127.0.0.1`, 375/390/1280/1440, EN/IT/FR, light + dark. Console **0**, **0**
horizontal overflow, store/PDP/cart/portal unaffected, language switcher (Phase 57)
unchanged. Screenshots in `docs/qa/phase59/`.

## Partial / next (honest)
This slice deliberately did **not** yet do: a full dropdown overhaul (sort/size/
colour/country beyond focus polish), a full forms overhaul (checkout/address book
field-level redesign), premium previews/skeletons everywhere, or **explainer videos**
(no suitable lightweight, watermark-free source was integrated; the motion is CSS/JS
text + reveal instead — declared, not faked). These remain for a follow-up phase.
