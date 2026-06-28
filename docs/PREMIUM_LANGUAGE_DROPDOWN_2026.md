# Premium language switcher — flag-inspired backgrounds (2026)

**Branch:** `fix/premium-language-dropdown-flag-backgrounds` (from
`feature/luxury-store-filters-motion-experience` @ `8804f45`). **No DB migration.**
No real orders/payments; Stripe TEST; Printify push OFF.

---

## 1. What was wrong before
- The navbar pill showed only the **language code** ("EN" / "IT" / "FR").
- The dropdown items showed the name **plus the code** — e.g. `Italiano (IT)`.
- The menu was a default Bootstrap dropdown with a flat list, no language identity.

## 2. What changed
- **Names only, no codes.** The pill now shows the native name (`English` /
  `Italiano` / `Français`) via `get_language_info ... name_local|capfirst`; the
  options show the name only — the `(EN)/(IT)/(FR)` chips and the old `lang-code`
  badge are gone.
- **Flag-inspired full background per language** (refined, not kitsch): each option
  carries a soft **full-width** gradient evoking the flag —
  - Italiano → green · white · red,
  - Français → blue · white · red,
  - English → sober navy · white · red (anglo, restrained).
  The active pill carries a fainter version of the same wash. CSS gradients only —
  **no flag images** (zero extra weight). A light central band keeps the white
  stripe legible; colour alphas are kept low so the **name stays readable**.
- **Premium menu shell**: rounded 14px, thin border, soft shadow, uppercase
  "Choose language" header, generous option padding/tap targets.
- **States**: hover lifts saturation slightly; the current language has an inset
  **gold ring + check**; focus shows a gold focus ring.
- **Dark mode**: dedicated gradient variants lift the colour bands and the central
  band so everything reads under light text.

## 3. Accessibility
- Button: `aria-haspopup`, `aria-expanded` (Bootstrap-managed), descriptive
  `aria-label="Change language"`.
- Current option: `aria-current="true"` + visible selected state (ring + check).
- Each option is a real submit `<button>` in a `set_language` POST form — full
  keyboard support; the globe/check icons are `aria-hidden`.
- Focus-visible rings on the pill and options; readable contrast in light & dark.

## 4. Mobile
The switcher lives in the collapsible navbar; on 375/390 the pill goes full-width
and the menu renders inline (`position:static`), full-width, no clipping, no
horizontal overflow, large touch targets.

## 5. i18n
New strings **Change language** / **Choose language** added in EN/IT/FR
(`Cambia lingua`/`Changer de langue`, `Scegli la lingua`/`Choisir la langue`),
compiled. Language names come from Django's `LANGUAGES` / `name_local`.

## 6. QA
`127.0.0.1:8799`, viewports 375/390/1280/1440, EN/IT/FR, light+dark. Console
**0 errors**, **0 overflow**. Names only confirmed (no codes). 7 screenshots in
`docs/qa/phase57/`.

## 7. Limits (honest)
- The dropdown still uses the existing **Bootstrap** toggle mechanism (jQuery
  already loaded) — restyled, not rebuilt as a bespoke vanilla widget.
- "English" uses a restrained navy/white/red (UK-leaning) wash rather than picking
  UK-vs-US; deliberately neutral.
- Flag washes are intentionally **subtle** (premium over literal); they evoke the
  flags rather than reproducing them pixel-accurately.
