# Customer Portal — Premium upgrade + E2E (2026)

**Branch:** `feature/customer-portal-e2e-premium-invoices-pdf` (from `release/staging-printify-fashion-store` @ `51c7cda`).
Premium customer portal (dashboard, orders, billing/receipts, PDF, wishlist,
search, addresses) + real end-to-end customer journeys across countries +
portal security tests. **No new DB migration** (the only migration in this train
is Phase 51's `0003`, already merged).

---

## 1. What was improved

| Area | Before | Now |
|------|--------|-----|
| Dashboard | KPI bug: "In progress"/"Completed" rendered **blank** (wrong context vars) | Fixed — all 4 KPIs populated; premium cards, Billing link in sidebar |
| Orders | Flat table, **no search/filter/sort** | Premium **order cards** + search (order # / product) + status filter + sort, filter-preserving pagination, per-order **Receipt** download |
| Billing | Did not exist (only a per-order PDF) | New **Billing & receipts** center (`/accounts/billing/`) with search/filter, **Preview + Download** per receipt, honest "not fiscal invoices" note |
| PDF | Basic text "Invoice", **English-only**, no logo | Premium **order receipt** (`orders/receipt_pdf.py`): Glitchy logo, brand palette, billed-to/order-info, **Paid/Pending** status, items, **Subtotal/Shipping/Discount/Tax/Grand total**, estimated delivery, footer disclaimer, **EN/IT/FR** from `order.language_code`. Inline **preview** (`?disposition=inline`) + download. Honest wording: **Receipt / Ricevuta / Reçu** (not a fiscal invoice). |
| Order detail | Totals missing **Shipping**; "PDF invoice" | Adds **Shipping** + Discount + **estimated delivery**; "Preview/Download receipt" |
| Wishlist | No search | **Search** within saved items + no-results state |
| Addresses | No field validation; free-text country | Country = **validated choice** (curated ISO list); required city/postal; phone format. Premium delete-confirm modal (already existed) |
| Dropdowns | Native OS `<select>` rectangle | **Premium custom dropdown** site-wide (`premium-select.js`): rounded popup, chevron, selected check, keyboard + ARIA, dark mode. Native `<select>` kept hidden for submission + a11y (value synced, `change` dispatched). |
| Mobile | Filter search box 260px tall (flex-basis on column axis); cards cramped; sidebar glued to heading | Fixed: search natural height, tight search↔dropdown gap, card separation, sidebar/heading spacing |

All new customer-facing strings are **EN/IT/FR**.

---

## 2. End-to-end journeys (tests)

`accounts/test_customer_portal_e2e.py` — **fictitious QA/TEST data only**, no real
orders, no real payments (Stripe/Printify never hit; orders are test fixtures, the
shipping estimate uses the local fallback with `SHIPPING_USE_PRINTIFY` off).

QA customers / cities / countries:

| Customer | City | Postal | Country |
|----------|------|--------|---------|
| Bram QA-BE | Bruxelles | 1000 | BE |
| Marco QA-IT | Milano | 20100 | IT |
| Camille QA-FR | Paris | 75001 | FR |
| Jordan QA-US | New York | 10001 | US |
| QA edge | Casablanca | 20000 | MA (unsupported) |

Flow per supported country: add address → cart → **shipping estimate** → portal
pages (dashboard/orders/billing/order detail) → **receipt PDF** (download +
inline) → **order search** → **wishlist** add → **delete address**. MA exercises
the unsupported path (estimate `unavailable`; address form rejects the country).

Cleanup: Django `TestCase` rolls back the DB per test (no residue). The live-QA
fixture user is removed at the end of the QA pass.

---

## 3. Shipping estimate (in the journeys)

BE/IT/FR/US return an available estimate (`local_fallback`/`cached_profile`;
`live_printify` when enabled). MA → `unavailable` (`country_unsupported`). Cost is
computed **server-side**; client-supplied prices are ignored; no order is created;
the estimate cache stores only a country + postal **prefix** (no PII).

## 4. Checkout

Guest and logged-in supported. Payments are **Stripe TEST** only; this phase
creates **no real order and no real payment** (E2E orders are fixtures). The
checkout shipping estimator is a `<div>` (not a nested form) — the estimate never
submits the order (Phase 52 fix, still covered).

## 5. PDF / receipts — honesty

The PDF is an **order receipt**, not a fiscal invoice (no VAT number / fiscal
fields), and is labelled as such in EN/IT/FR. It renders only customer-facing
data and **never** the internal Printify ids/status or our cost fields
(`cost_production`, `cost_shipping`, `payment_fee`) — covered by a test that
injects those values and asserts they are absent from the PDF stream.

## 6. Security / data isolation (tests)

`PortalSecurityTests`: portal requires login; a user **cannot** view another
user's order (404), download another user's receipt (403), or delete another
user's address (404); orders/billing lists show only the owner's data. Address
CRUD is `@require_POST` + `user`-scoped. No PII or secrets in reports/logs.

---

## 7. Tests run

`check` ✅ · `makemigrations --check` (none) ✅ · full `test` suite ✅ · `compilemessages it/fr` ✅ · `collectstatic` ✅ · `staging_check` ✅ · `integration_status --staging` = 2 rotation gates (expected). 24 new portal/E2E/security tests.

## 8. Live QA

Local `127.0.0.1:8799`, viewports 390 + 1280, EN/IT/FR, light + dark. Console 0
errors, 0 horizontal overflow. Screenshots in `docs/qa/phase53/`.

---

## 9. What works · partial · missing

**Works:** premium dashboard/orders/billing/order-detail/wishlist/addresses;
premium PDF receipt (EN/IT/FR, logo, status, totals) with preview + download;
order/receipt/wishlist search + status filter + sort; address validation;
site-wide premium dropdowns; data isolation; E2E across BE/IT/FR/US + MA edge.

**Partial / fallback:** shipping estimate uses cached/fallback by default
(`SHIPPING_USE_PRINTIFY` off at rest); receipt is an order receipt, **not** a
fiscal invoice; wishlist does not store per-variant saves; PDF logo embed makes
the file ~300 KB.

**Missing for production:** real fiscal invoicing (VAT, sequential numbering) if
required; account/profile-settings page; payment-methods management; real staging
host + `migrate` for Phase 51's `0003`; key rotation; live shipping QA on a public
URL; broader real catalog.
