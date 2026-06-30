# Customer Portal Intelligence + Wishlist Facets + Legacy Premium Sweep (Phase 63, 2026)

**Branch:** `feature/customer-portal-intelligence-wishlist-facets-legacy-polish` (from
`release/staging-printify-fashion-store` @ `b16c664`). **No DB migration** — every feature
is built on existing models/fields. No real orders/payments; Printify push/sync OFF.

## 1. What was missing
Phase 62 made the portal premium and added basic order/billing/wishlist filters. But the
wishlist still only had search + sort (no real facets), the activity timeline only covered
orders/receipts/address, the sidebar had a single badge, and the **login/register pages
were still raw Bootstrap**.

## 2. Wishlist facets (the centerpiece — `wishlist/facets.py`)
Advanced, **data-driven** facets over a user's saved items, built by filtering a Product
queryset scoped to the saved product ids (so it is **ownership-safe** and **N+1-free**):
- **Category** (dropdown, counts), **Colour** + **Size** (chips with counts, from
  `Variation`), **Price** min/max (validated, bounded), **On sale** (`compare_at_price >
  price`), **Multi-image** (`gallery` count > 1), **Recently saved** (`WishlistItem.created_at`).
- **Quick chips** (On sale / Multi-image / Recently saved, with counts) + **removable
  active chips** + **Clear all** (via the store `qs_set`/`qs_remove` tags).
- **Querystring-persistent**, **pagination-preserving** (12/page), **result count**,
  collapsible advanced panel (native `<details>` — mobile friendly), light+dark.
- Facet options are computed from **all** saved products (so they stay visible while
  filtering) via aggregate queries — never a per-item loop.

Every facet shows **only when the data exists** (e.g. no colour facet if no saved product
has colour variations). All inputs are validated/whitelisted (no ORM field/order_by
injection).

## 3. Wishlist quick actions + card (`_saved_card.html`)
Each saved card now has: **Quick view** (reuses the global quick-view modal),
**View** (PDP), **Remove** (wishlist toggle — now a visible icon button), a **sale price**
(strikethrough `compare_at_price` + a "Sale" badge), and a **multi-image carousel**
(reuses the Phase 61 product-card gallery) for products with several images. Add-to-cart
is intentionally routed through quick view / PDP so variant-required products never get
added without a size/colour.

## 4. Activity timeline (richer, still real)
The dashboard timeline now also includes **wishlist saves** (real `WishlistItem.created_at`
timestamps), alongside orders, receipts and the last address update — newest first, capped
at 7. **Option A** (no migration): no `CustomerActivityEvent` model was added, because the
real signals already available are enough and avoid an unnecessary schema change. (A
dedicated event model remains a documented future option if richer auditing is wanted.)

## 5. Portal navigation (`accounts/context_processors.py` + `_sidebar.html`)
The sidebar now shows **count badges** for orders, receipts and addresses (alongside the
existing wishlist badge), plus the existing elegant active states. Counts come from a
**lazy** context processor (`SimpleLazyObject`): the COUNT queries run only when the
sidebar actually reads them, so non-portal pages (store, home, PDP) pay **nothing**.

## 6. Portal utilities
- **Copy order number** on the order detail (clipboard, with a "Copied" confirmation) via
  a tiny vanilla `portal.js`.
- Not added (honest): "Reorder/Buy again" (variant-safety + cart-merge risk),
  "Download all receipts" (would need a zip/streaming job), "Recommended from saved" — all
  documented as follow-ups rather than faked.

## 7. Legacy premium sweep
- **login.html** and **register.html** rewritten from raw Bootstrap to a premium auth card
  (serif title, premium fields, gold links, error summary) with a **password visibility
  toggle** (accessible, localized aria-labels).
- **order_detail** gained the copy utility. `address_form` / `transactions` were already
  premium and left intact.

## 8. Design system
A focused **PHASE 63 CSS block** (active chips, facet chips/panel, enhanced saved card,
auth, password toggle, copy button) — light+dark, mobile breakpoints, focus-visible,
`prefers-reduced-motion`. **No `border-color: var(--border-strong)`** (the Phase 49/61
guard), no needless `!important`.

## 9. Forms
Premium auth fields, grouped layout, error summary + per-field errors, **password toggle**,
proper autocomplete attributes, no nested forms, CSRF preserved.

## 10. Performance / queries
- `wishlist/services.items()` now `prefetch_related("product__gallery")` (cover/hover and
  the carousel read the cache — no N+1). The single-image card path reads the prefetched
  gallery directly instead of `cover_image()` (which re-queries).
- Facet building uses **aggregate** queries (categories/colours/sizes/price/sale/multi),
  not per-item loops; `matching_product_ids` runs one DB-side filter.
- Sidebar counts are lazy; the dashboard wishlist loop is bounded `[:3]` + `select_related`.
- A test asserts **0 extra queries** reading the gallery cover per card.

## 11. Security / ownership
Facets filter a Product queryset scoped to the **user's own** saved product ids — no
cross-user leak, proven by a test where another user filtering by the same facet sees
nothing. `portal_counts` returns `{}` for anonymous users. All inputs validated. CSRF on
all forms. No PII in reports or the PII-safe QA screenshots (throwaway "QA Demo" accounts,
deleted afterwards). No PII written to `localStorage` (only the theme toggle, pre-existing).

## 12. i18n
~25 new/updated strings (facet labels, auth, copy, pagination) in **EN/IT/FR**, compiled
and verified (facet chip labels use `gettext_lazy`).

## 13. QA
Local `127.0.0.1`, **375/390/1280/1440**, EN/IT/FR, **light + dark**, **console 0**,
**0 overflow**. 12 PII-safe screenshots in `docs/qa/phase63/`.

## 14. Limits (honest)
- Activity timeline is **derived** (no event model); shows orders/receipts/address/wishlist,
  not e.g. "logged in".
- Utilities: reorder, download-all-receipts, recommendations are **not** implemented
  (documented follow-ups), to avoid faking or risking variant/cart correctness.
- Facets cover category/price/colour/size/sale/multi/recent; brand/material facets aren't
  modelled in the data, so they're omitted (only real facets are shown).
- The legacy sweep prioritised the worst offenders (login/register); a few low-traffic
  legacy templates remain on the backlog.
