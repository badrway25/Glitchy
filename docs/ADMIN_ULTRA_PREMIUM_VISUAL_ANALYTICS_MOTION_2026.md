# Ultra-Premium Admin: Visual Analytics + Motion (Phase 69, 2026)

**Branch:** `feature/admin-ultra-premium-visual-analytics-motion` (from
`release/staging-printify-fashion-store` @ `254908b`). **No new migration.** No deploy, no key
rotation, Printify publish/order/sync OFF. No CDN.

## 1. Goal
Turn the (already-functional) Unfold admin into a **luxury "Commerce Studio"** decision panel:
sophisticated palette, sober motion, and **real charts** (health score, distributions, sync
health, orders trend, category readiness) — while keeping the security posture untouched.

## 2. Design system (`greatkart/static/glitchy_admin/premium.css`)
Progressive enhancement scoped to `.gl-*` classes (never fights Unfold's own components).
- **Palette:** deep ink / espresso, champagne + gold, ivory surfaces, soft bronze, muted
  emerald (ok), warning amber, destructive ruby — all as CSS variables with a **refined dark
  theme** (warm espresso surfaces, not flat black) via `html.dark`.
- **Surfaces:** soft borders, layered shadows, `--gl-radius` cards with a subtle gold-tinted
  accent gradient; airy spacing; tabular-nums for figures.
- **Components:** KPI card, health ring, donut, progress bars, sparkline, severity badges,
  sync KV rows with status pulses, issue rows with "Fix now" links, quick-action pills, and
  elegant empty states.

## 3. Motion (`greatkart/static/glitchy_admin/motion.js`)
Vanilla, no dependency. IntersectionObserver **reveal**, KPI **count-up**, bars/sparkline
**grow from 0**, health-ring **stroke-dashoffset draw**. Crucially it is *pure enhancement*:
the dashboard renders complete **without JS** because every value is computed server-side and
written as an inline width/offset. `prefers-reduced-motion` (and no-IO) → values shown
instantly, **no animation, no layout shift**. Wired via Unfold's `UNFOLD["STYLES"/"SCRIPTS"]`.

## 4. Analytics (`greatkart/admin_ext.py`, all aggregate / no PII / no secret)
- **Catalog Health Score (0–100)** — average of 7 "ok %" dimensions (images, prices,
  categories, descriptions, variants, sync freshness, sync errors) → an **SVG ring** +
  per-dimension **progress bars** + an **issues list** with severity badges and deep-links to
  the matching product filter ("Fix now").
- **Product Status** — Active/Hidden and Printify/Manual **conic-gradient donuts** with
  linked legends.
- **Printify Sync Health** — connection pulse, token present (yes/no — never the token),
  sync mode, stale count, errors, and **"publish off / orders off"** safe-default badges;
  elegant empty state when no account is configured.
- **Orders (30d)** — count + gross + a **7-day sparkline** (no PII, never lists an order).
- **Category Readiness** — top categories with a readiness % bar.
- **Wishlist demand** — total + top saved products (public names only).

The charts are **CSS/SVG only** (conic-gradient donuts, CSS-width bars, an SVG stroke ring) —
**no Chart.js, no CDN**. Each carries an `aria-label` / `role="img"` text alternative.

## 5. Security
- No token, key, or PII in the dashboard HTML/JS/context (test-asserted; a config-with-token
  test proves the token never appears).
- Printify `allow_product_publish` / `allow_order_creation` remain **OFF**; the dashboard only
  *displays* their state, it never flips them.
- No external/CDN reference in the CSS/JS/template (test-asserted).

## 6. Accessibility
Charts have `role="img"` + descriptive `aria-label`; progress values are shown as text
alongside the bars; status is conveyed by label + pulse (not colour alone); focus states
preserved; `prefers-reduced-motion` fully honoured; mobile stacks (ring above bars, donuts
column) with 0 overflow.

## 7. Performance
Dashboard = a handful of aggregate `count()` / grouped queries (no per-card query loop, no
N+1). Orders sparkline is 7 small counts. CSS ~9 KB, JS ~2 KB, both static (whitenoise). No
CLS (server-rendered final values; motion only replays them).

## 8. QA
Local admin, 1440 + 390, **light + dark**, reduced-motion emulated, **console 0**, **0
overflow**, **no token/PII in HTML**. 12 secret/PII-safe screenshots in
`docs/qa/phase69_admin_visual/`.

## 9. Limits (honest)
- The deep visual system (`.gl-*`) is applied to the **dashboard** (the primary surface);
  product/order/Printify **list & change** views keep the Unfold styling + the badges from the
  previous phase (a full per-model change-form redesign was out of scope).
- Charts are intentionally lightweight CSS/SVG — great for these KPIs, but not a general
  charting lib (e.g. no zoomable time-series). A vendored Chart.js could be added later if a
  richer chart is ever needed (still no CDN).
- No new migration; the analytics read existing models.
