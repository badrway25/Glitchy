# Premium dynamic homepage — wide Pexels hero & motion (2026)

**Branch:** `feature/premium-dynamic-homepage-pexels-hero` (from
`fix/premium-language-dropdown-flag-backgrounds` @ `0751fb2`). **No DB migration.**
No real orders/payments; Stripe TEST; Printify push OFF; shipping fallback OFF.

---

## 1. Problem (owner feedback)
The static homepage imagery wasn't premium enough: the hero was a single JPG
constrained to a 1280px container (not full-bleed), there was no responsive/WebP
delivery, the only other photo was a generic folded-linen shot, and there was no
real motion beyond a copy fade-in. The ask: a **wide, dynamic, editorial** hero,
**appropriate premium images via the Pexels API**, optimized assets, **elegant JS
motion**, and homepage sections that feel less static — without heavy animations or
performance regressions.

## 2. Pexels API (secure, reproducible)
A management command, `storefront/management/commands/fetch_pexels_home_assets.py`:
- reads the key **only** from `PEXELS_API_KEY` (env) and **never prints it**;
- pins each image by **Pexels photo id** (not a random search) so re-runs are
  deterministic;
- crops + re-encodes to responsive **WebP + JPEG** under
  `greatkart/static/images/home/pexels/`;
- writes a secrets-safe `CREDITS.json` attribution manifest;
- is a **dry run** unless `--apply` is passed.

Five images were curated from ~40 candidates across 8 queries (hero, editorial,
collection moods). Full attribution: `docs/image-sources/PEXELS_HOME_ASSETS_2026.md`.
**The site serves local assets only — no Pexels hotlink at runtime.** If the API is
unavailable, the committed local renditions remain the source of truth (no build-time
network dependency).

## 3. Hero redesign (wide, full-bleed)
- **Full-bleed** `.hero-x` section (breaks out of the 1280 container), height
  `clamp(540px, 80vh, 840px)`.
- **Art-directed `<picture>`**: a dedicated **mobile portrait** crop
  (`hero-editorial-mobile-900`, 900×1120) under 768px, and **responsive desktop**
  widths (`-1280`, `-2000`) with `sizes="100vw"`, WebP first with JPEG fallback.
- **Refined gradient scrim** (left + bottom) so the white copy reads on any frame.
- Headline `clamp(2.4rem, 6vw, 4.8rem)`, sub, **dual CTA** ("Shop the collection" →
  store, "View collections" → collections) + a 3-item **trust line**.
- Dark editorial B&W image → pairs with gold accents; works identically in light and
  dark themes (the hero is image-driven, theme-agnostic).
- **LCP-friendly**: `<link rel="preload">` (WebP, `fetchpriority="high"`),
  `width/height` on the `<img>` (no CLS). The hero is the only image **not** lazy.

## 4. Homepage sections (less static)
- **"The Edit"** — a new 3-card editorial band mapped to **real categories**
  (Shirts / T-shirts / Jackets), each with a premium portrait image, gradient,
  kicker + title, hover reveal of an "Explore →" affordance. Links resolve by slug
  in the view and **degrade to `/store`** if a category is missing (no hard 404).
- **Editorial split** ("Quality you can feel") now uses a premium soft-cotton
  texture via `<picture>` (WebP + mobile source) instead of the old generic shot.
- Existing Popular / Promise / Latest sections retained; order re-flowed for a more
  editorial rhythm.

## 5. Motion (`home-motion.js`, vanilla, ~1.6 KB)
- **Hero parallax**: rAF-throttled `translate3d` on the hero picture while in view
  (the picture is oversized 116% so edges never reveal).
- **Ken Burns**: subtle CSS scale on the hero image (one-shot, 22s).
- **The Edit reveal**: IntersectionObserver staggered fade-up.
- **Subtle tilt**: ≤2.6° perspective tilt on cards, **desktop fine-pointer only**.
- All gated on `prefers-reduced-motion` (CSS **and** JS); progressive enhancement
  (content is fully visible without JS); safety-net reveal on `load`; passive
  listeners; single rAF guard (no listener pile-up / layout thrash).

## 6. CSS
New Phase 58 block in `premium.css`: full-bleed hero, gradient scrims, editorial
typography, `.btn-ghost-light`, the `.edit-grid`/`.edit-card` system, `<picture>`
fill rules for the split, and a reduced-motion guard. Responsive at 375/390 (cards
stack, hero copy full-width, CTAs stretch) and 1280/1440. Light + dark.

## 7. Accessibility
- Decorative gradients are `aria-hidden`; the hero section, trust list, and scroll
  cue carry `aria-label`s.
- **Every** Pexels `<img>` has descriptive `alt` (EN/IT/FR via `{% trans %}`).
- High-contrast white copy on the dark scrim; gold focus ring on the edit cards.
- No carousel / no autoplay; motion is optional and reduced-motion-safe.

## 8. Performance
- Hero LCP asset: **13 KB WebP / 45 KB JPEG** at 2000px (dark, low-detail → tiny).
- Largest asset (fabric 1200): 171 KB WebP / 213 KB JPEG — under the 300 KB target.
- `width/height` everywhere (no CLS), preload + `fetchpriority` on the hero, lazy +
  `decoding="async"` on every non-LCP image, WebP with JPEG fallback.

## 9. i18n
New customer-facing strings (hero aria/alt, "The edit", "Find your look", card
kickers/titles/alt, "View collections", etc.) added and translated in **EN/IT/FR**,
compiled. Category labels in the cards are editorial UI labels via `{% trans %}`,
decoupled from DB category names.

## 10. QA
Local `127.0.0.1`, viewports 375/390/1280/1440, EN/IT/FR, light + dark. See the
phase report for the full matrix and screenshots in `docs/qa/phase58/`.

## 11. Limits (honest)
- Imagery is **stock** (Pexels), not a brand photoshoot — curated to look premium
  and on-brand, but it is not bespoke product photography.
- The hero is a single editorial still (with motion), **not** a multi-slide
  carousel — a deliberate choice for stability/accessibility/LCP.
- "English/After dark/etc." imagery evokes moods; the three Edit cards map to three
  real categories (Shirts/T-shirts/Jackets), not to every catalog category.
- Everything is verified **locally** (no public-URL QA, no Lighthouse on a real host).
