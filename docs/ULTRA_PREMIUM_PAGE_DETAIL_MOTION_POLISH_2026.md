# Ultra-Premium Page Detail + Motion Polish (Phase 64, 2026)

**Branch:** `feature/ultra-premium-page-detail-motion-polish` (from
`release/staging-printify-fashion-store` @ `5414301`). **No DB migration.** No real
orders/payments; Printify push/sync OFF.

## 1. Initial problem
Six pages still read as "simple" / unfinished next to the rest of the store:
`/wishlist/saved/`, `/accounts/login/`, `/accounts/register/`, `/store/`,
`/accounts/dashboard/`, `/accounts/addresses/new/`. The brief asked for a *visible* jump
in perceived quality — not a colour tweak — across header, cards, forms, filters, buttons,
icons, empty states, microcopy, spacing, motion, hover/focus, mobile and dark mode.

## 2. Pages treated
All six, plus a shared design-system + motion pass that benefits the whole site.

## 3. Design system detail pass (shared utilities)
A new **PHASE 64 block** in `premium.css`, reused across the six pages (less duplication,
more consistency):
- `.lux-head` / `.lux-eyebrow` / `.lux-title` / `.lux-sub` — an editorial page header
  (gold eyebrow rule + serif clamp title + subtitle + right-aligned actions).
- `.lux-summary` / `.lux-stat` — a summary stat-pill bar (tabular-nums values).
- `.lux-empty` — a luxury empty state (gradient icon tile, serif heading, CTA row).
- `.lux-panel` / `.icon-tile` — refined surface + premium icon tile.
- `.auth-split` / `.auth-side` / `.auth-benefit*` — split auth layout + brand/benefit panel.
- `.addr-*` — grouped address-form sections, premium inputs, an elegant default switch.
- `.guest-note` — a premium replacement for the raw Bootstrap guest alert.
No `border-color: var(--border-strong)` (the Phase 49/61 guard), minimal `!important`,
focus-visible everywhere.

## 4. Refined motion
`greatkart/static/js/page-polish-motion.js` (vanilla, progressive) **reuses** the existing
`[data-reveal]` / `.is-visible` system and adds only what was missing:
- **Staggered reveal**: `[data-reveal-stagger]` cascades its children (cards, KPIs, quick
  actions) via CSS `nth-child` delays once the container scrolls in.
- **KPI count-up**: `[data-countup]` animates from 0 to the server value on first view.
Both are **`prefers-reduced-motion` safe** (instant, no animation), have **no-IO
fallbacks** (content shown immediately if IntersectionObserver is missing), **unobserve**
after firing (no leak), and cause **no layout shift** (KPI numbers use `tabular-nums`).

## 5. Wishlist
Was: plain `dash-top` heading + tiny result count. Now: **editorial `.lux-head`** (YOUR
COLLECTION eyebrow + serif title + subtitle), a **summary bar** (Saved / Filtered / On sale
/ Multi-image, with a count-up on the saved total), a **premium guest note**, **staggered
card reveal**, and **luxury empty / no-results states** with their own copy and CTA rows.

## 6. Login
Was: a single centered card. Now: a **split layout** — a dark brand panel (gold eyebrow,
"Welcome back." serif, a reassurance line + lock icon, warm radial glow) beside the form,
collapsing to a clean full-width card on mobile. Premium fields, password toggle, gold
links. CSRF untouched.

## 7. Register
The same split, with a **member-benefits panel**: four real benefit cards (Faster
checkout, Saved addresses, Order receipts, Saved items) — no invented features. Grouped
fields, two password toggles, gold "Register" CTA, error summary preserved. One form, no
nesting.

## 8. Store
Already premium, so a **light, low-risk pass**: the no-results state adopts the luxury
`.lux-empty` styling and the store header gains a subtle reveal. The product grid keeps its
existing reveal (store-luxury.js), the gallery carousel and prefetch are untouched.

## 9. Dashboard
A premium **`.lux-head` hero** ("Hi, {name}" + eyebrow + subtitle), **count-up** on the
integer KPIs, and **staggered** quick-actions + KPI grid. Alerts, activity timeline and
the orders table keep their Phase 62/63 content; with no orders the page still reads
premium (alerts + empty state).

## 10. Address form
Was: an inline `<style>` block + a flat field grid + a Bootstrap checkbox. Now: an
editorial header and **three grouped sections** (Contact / Shipping address / Delivery
preferences) each with an icon tile + helper line, **premium inputs** with a gold focus
halo, an **elegant default-address toggle switch**, and clear Save / Cancel CTAs. Single
non-nested form, CSRF preserved, every AddressForm field rendered.

## 11. Accessibility
Visible focus rings throughout; icon-only buttons keep aria-labels; the default toggle is a
real `<input type=checkbox>` styled as a switch (keyboard + screen-reader safe); headings
are hierarchical; the password toggle keeps localized aria-labels; reduced-motion fully
respected; mobile tap targets preserved.

## 12. Performance
No new queries (the wishlist `total_saved`/`filtered_count` are derived from data already
fetched). Gallery prefetch intact (no N+1). Motion is one tiny vanilla file; reveals
unobserve after firing. No CLS (tabular-nums); images stay lazy.

## 13. i18n
~31 new strings (page copy, benefits, address sections, empty states) in **EN / IT / FR**,
compiled and verified.

## 14. QA
Local `127.0.0.1`, **375/390/1280/1440**, EN/IT/FR, **light + dark**, **console 0**,
**0 overflow**, reduced-motion verified (no element stuck hidden). 15 PII-safe screenshots
in `docs/qa/phase64/`.

## 15. Limits (honest)
- The **store** received a deliberately light touch (it was already premium) — a deeper
  toolbar/filter-drawer redesign is a possible follow-up.
- Count-up runs only on integer KPIs (not the € total) to keep it clean.
- The split auth side panel is desktop-only (hidden < 768px by design) so mobile stays
  fast and uncluttered.
- No new features or data were introduced — only presentation and motion.
