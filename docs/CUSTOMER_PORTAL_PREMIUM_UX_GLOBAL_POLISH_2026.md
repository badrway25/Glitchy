# Customer Portal Premium UX + Global Page Polish (Phase 62, 2026)

**Branch:** `feature/customer-portal-premium-ux-global-page-polish` (from
`release/staging-printify-fashion-store` @ `4847549`). **No DB migration** — every
feature is built on existing models/fields. No real orders/payments; Printify
push/sync OFF.

## 1. Initial problem
Phase 53 gave the portal a solid skeleton (sidebar, order list with search/status/sort,
billing, addresses with default, wishlist search). But the **dashboard was thin** (4
KPIs, a table) and the **filters were basic** (no date/total range, no quick chips, no
result count, no billing summary). The owner asked for a genuinely more *useful* portal —
practical filters, a useful dashboard, premium empty states, efficient queries, and
ownership security — plus a coherent global polish.

## 2. Dashboard (accounts/views.py `dashboard`, templates/accounts/dashboard.html)
- **6 KPI cards** (was 4): Total orders, Spent, In progress, **Receipts available,
  Saved addresses, Saved items** — all from real per-user queries.
- **Quick actions** row: View orders · Receipts · Addresses · Saved items · Continue
  shopping.
- **Smart alerts** (only when actionable): "*N* receipts ready to download → billing",
  "Add a delivery address" (when none), "*N* items saved for later → wishlist".
- **Recent activity timeline** derived from **real data only** — orders placed, receipts
  available, last address update — sorted by date, capped at 6. No event model is
  invented; if there's nothing, the section is simply hidden.
- **Premium empty state** when the customer has no orders.
- **N+1 fixed**: `recent_orders` now `select_related("payment")` (the table reads the
  payment method per row at zero extra cost).

## 3. Order filters (accounts/views.py `_filter_sort_orders`, `my_orders`)
Extends the shared helper with **date range** (`date_from`/`date_to` on `created_at`),
**total range** (`total_min`/`total_max` on `order_total`), and a **receipt** toggle
(`payment` present). Plus **quick chips** (All / Confirmed / Packed / Completed / With
receipt), a **result count**, and a collapsible "More filters" panel (native
`<details>` — mobile-friendly, no JS). Every input is **validated/whitelisted**
server-side (sort against a whitelist, amounts must be finite and ≥ 0, dates via a fixed
format), all **querystring-persistent** and **pagination-preserving**.

## 4. Billing / receipts (accounts/views.py `billing`, templates/accounts/billing.html)
Same enhanced filters + an honest **summary** over all the user's orders: **paid orders**
(+ total spent), **receipts available**, **awaiting payment**. Wording stays honest —
"order receipts (not fiscal invoices)". Receipts exist for paid orders; the per-row
download/preview is unchanged.

## 5. Wishlist (wishlist/views.py `saved_items`, templates/wishlist/saved_items.html)
Adds **sort** (Recently added / Name A–Z / Price low→high / high→low) alongside the
existing search, plus a **result count** (counts both the wishlist and save-for-later
sections). Cards/galleries unchanged.

## 6. Address book (accounts/views.py `address_list`, templates/accounts/address_list.html)
Adds **search** by city / country / postal code / name. The **default badge** and
**"set as default"** action already existed (`Address.is_default`) and are preserved —
no migration needed.

## 7. Activity / timeline
Built **from existing data**, not a new events table: order-placed, receipt-available
and address-updated entries, newest first. This is the honest, no-invented-data
approach the brief asked for.

## 8. Global page polish
A new **PHASE 62 CSS block** in `premium.css`: dashboard alerts, quick-action tiles,
the activity timeline, the 6-up KPI grid, the filter quick-chips and the collapsible
advanced-filter row — all with **light + dark** variants, mobile breakpoints, and
`prefers-reduced-motion` guards. The store/home and Phase 61 button/gallery work are
unchanged and verified intact. This pass is **surgical** (portal-focused) rather than a
site-wide re-theme.

## 9. Performance / queries
- Dashboard recent orders `select_related("payment")` (no N+1).
- Billing summary computes the paid count **once** and reuses it (no duplicate COUNT).
- Order/billing base querysets keep `select_related("payment")` through all filters.
- Wishlist keeps `select_related("product","product__category")`.
- Address queries are a single user-scoped query.
- Tests assert **0 extra queries** reading payment per dashboard row.

## 10. Security
Every list is **scoped to `request.user`** before any filter runs. `order_detail` /
address edit/delete/set-default use `get_object_or_404(..., user=request.user)`. Filter
inputs can't inject ORM fields (sort whitelisted, amounts/dates parsed safely, `q`
capped). Tests prove a user can't see another user's orders or open another user's order
detail, and that every portal page requires login. No PII in reports or the PII-safe QA
screenshots (a throwaway "QA Demo" account, deleted afterwards).

## 11. i18n
~40 new customer-facing strings (incl. two `blocktrans count` plurals) translated in
**EN / IT / FR** and compiled. Verified rendering in all three languages.

## 12. QA
Local `127.0.0.1`, **375/390/1280/1440**, EN/IT/FR, **light + dark**, **console 0**,
**0 overflow**. 12 PII-safe screenshots in `docs/qa/phase62/`. Note: the site uses a
`height:100%` body-scroll model (fixed navbar), so Playwright's *full-page* capture can't
scroll the portal on mobile — content was verified present (opacity 1, real heights,
single-column KPI grid) via DOM inspection and viewport shots.

## 13. Tests
`accounts/test_phase62_portal.py` — 17 tests: dashboard premium render + real KPIs +
no-N+1; order date/total/receipt filters; chips + count; querystring persistence;
**invalid/negative/non-finite inputs are safe**; billing summary; wishlist sort; address
search; **ownership** (orders scoped, order-detail 404 for others, login required); i18n
EN/IT/FR; checkout-redirect regression. Full suite green.

## 14. Limits (honest)
- The **activity timeline is derived** from orders/receipts/address — there is no
  per-event audit model, so it shows those real signals, not (e.g.) "logged in" or
  "profile edited".
- **Wishlist filters** are search + sort; richer facets (category/colour/size/price-range
  chips reusing the store filter UI) are a natural follow-up, not done here.
- The global polish is **portal-focused and surgical**; a full design-token sweep of
  every legacy page is out of scope for this phase.
- Receipt availability = "order has a payment"; there is no separate `is_paid`/PDF-ready
  flag (avoided a migration).
