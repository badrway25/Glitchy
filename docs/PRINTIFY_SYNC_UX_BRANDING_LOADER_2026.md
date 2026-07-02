# Printify Sync UX Diagnostics + Glitchy Branding + Premium Loader (2026)

**Branch:** `fix/printify-sync-import-branding-loader-ux` (from
`release/staging-printify-fashion-store` @ `e103893`). **New migration `0007`.** No deploy, no
secret exposure. Publishing + order creation stay OFF; sync is local-DB only.

## 1. Problem reported (live site)
"Connected" in the Printify admin, but **no products appeared**. The `PrintifySyncState` page
was a confusing technical table. The admin showed a generic **settings** icon, not the Glitchy
logo, and the favicon was stale. The Discover/Test/Dry-run/Sync actions gave **no loader/feedback**.

## 2. Why "Connected" wasn't enough — and why no products showed
A 6-reader diagnosis found the root cause was **our own over-aggressive hide policy** added in
the previous phase. "Sync products now" (`import_catalog_from_config(apply=True)`) hid **any**
product missing price **or** image **or** category (`is_available=False`), and the storefront
only shows `is_available=True`. So the owner saw `created > 0` but **0 products in the store**,
with only a transient one-line message — no way to see why. Secondary contributors: products
with no enabled-variant price → `price=0` → hidden; a non-public fallback category → category
page 404; and the result was never persisted for re-reading.

## 3. What "Sync products now" does now
- Imports via `GET /v1/shops/{numeric_id}/products.json` (paginated) with the **admin config**
  credentials — never the env token, never publishes, never creates an order.
- Reuses the existing `_upsert_product` mapping (title, description, price/cost from the enabled
  variant, category, `visible`→available, blueprint/provider, tags, images→gallery,
  variants→colour/size).
- **New hide policy:** only **unsellable** products (no price) are hidden. Incomplete-but-
  sellable products (e.g. missing image) are imported **visible and flagged for review**, so a
  connected shop's catalogue actually appears. Each flagged product records a structured reason
  (`no price` / `no image` / `no category`).
- The fallback category is always **public** (no 404 on category browse).

## 4. Report — persistent, owner-friendly
`SyncLog` gained `skipped_count`, `hidden_count`, `missing_price_count`, `missing_image_count`,
`shop_id`, `dry_run`, and a `detail` JSON (safe: to-review slugs + reasons + a few samples).
Every operation now:
- shows a clear message ("Sync done: 12 created, 3 updated, 6 hidden (no price — can't be sold),
  N need review" — or "imported 0 products; the shop may be empty or all drafts"),
- persists a **report card** on the Printify account page (count pills + "needs review"
  breakdown + links: **View hidden products**, **All products**, **Full report**),
- and a `SyncLog` **drill-down** page listing each to-review product (linked to its admin page)
  with its reason.

## 5. Sync Monitor (was `PrintifySyncState`)
Kept (Option B) and turned into a readonly **"Printify Sync Monitor"**: an explanation ("this
page tracks the background/manual sync state… read-only"), health fields (last tick/full sync,
backoff, consecutive errors, last error status, products synced total), the recent product
syncs, and links back to the account + products-needing-review. Not editable (the daemon owns
the lock/backoff): `has_change_permission=False` → Django renders it in view-only mode.

## 6. Loader / modal system
`greatkart/static/glitchy_admin/ops-modal.{js,css}` (registered via `UNFOLD['SCRIPTS']`/
`['STYLES']`). Progressive enhancement: the ops forms are synchronous POST→redirect, so without
JS they still work (Django messages). With JS, submitting shows a **premium full-screen overlay**
(dimmed blur, gold spinner, operation title, a stepped checklist: Connecting → Reading →
Mapping → Updating local database → Building report) that persists until the server redirect
navigates. Vanilla JS (no Alpine, to avoid Unfold's modal namespace), reuses the `.gl-*` tokens,
**reduced-motion safe** (no spin/step animation when the user prefers reduced motion), no CDN.

## 7. Glitchy logo + favicon
`UNFOLD` now sets `SITE_LOGO` (light/dark nav wordmark), `SITE_ICON` (square monogram mark),
`SITE_SYMBOL='storefront'` (Material-Symbol fallback only) and `SITE_FAVICONS` (favicon.ico) via
deferred `static()` callables. The admin sidebar now shows the **Glitchy** wordmark instead of
the generic settings icon; the favicon is the Glitchy asset. The storefront favicon was already
correct. Assets already existed under `greatkart/static/images/brand/` + `images/favicon.ico`.

## 8. Security
No token, no `PRINTIFY_CONFIG_KEY` in any HTML/JS/JSON/message/log/screenshot (only masked
last-4 + fingerprint). No PII in reports/screenshots (demo data used fake email/tokens). No
publish/order endpoint is ever called (test-asserted). All operations are POST + superadmin-
gated (non-superadmin → 403). `allow_product_publish`/`allow_order_creation` stay OFF.

## 9. Migration / deploy
`printify_integration/0007` (SyncLog richer counts + `detail` JSON + Sync Monitor rename).
**Deploy requires `migrate`** + `collectstatic` (new ops-modal assets + logo/favicon wiring).
No new dependency.

## 10. QA
Local admin, light + 390 mobile, **console 0**, no overflow. Verified: Glitchy logo (no
settings icon), favicon.ico wired, loader overlay with steps, persistent report with pills +
reasons + links, Sync Monitor readonly+explained, and a **mocked** import (real code path, no
real Printify call, real token never used) creating 4 products → **3 visible on the store, 1
hidden (no price)** — the exact behaviour that fixes "connected but no products". 9 secret/PII-
safe screenshots in `docs/qa/printify_sync_ux_branding/`.

## 11. Troubleshooting (owner)
- *Connected but 0 products?* Open the account page → **Latest sync report**. It shows created/
  hidden/skipped + "needs review" reasons and a **View hidden products** link.
- *All hidden?* They likely have no price (can't be sold) — fix prices in Printify and re-sync,
  or set a price locally.
- *"imported 0 products"* → the shop is empty or every product is a draft in Printify.
- *Discover/Test failed (401/403/429)* → token invalid/expired/missing scopes/rate-limited.

## 12. Limits
- Live Test/Sync need a real valid token on the server; local QA uses mocks (never the real
  token).
- The background daemon `run_tick` still reads the env token (unchanged) — admin import uses the
  config token; wiring the daemon to the active config is a follow-up.
- Remote product images are downloaded best-effort; if a CDN URL is unreachable the gallery row
  keeps the URL metadata without the file (product still imports).
