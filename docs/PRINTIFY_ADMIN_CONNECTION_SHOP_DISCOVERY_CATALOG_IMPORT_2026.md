# Printify Admin: Connection + Shop Discovery + Catalog Import (2026)

**Branch:** `fix/printify-admin-connection-shop-discovery-catalog-import` (from
`release/staging-printify-fashion-store` @ `c939186`). **New migration `0006`.** No deploy, no
secret exposure. Publishing + order creation stay OFF.

## 1. Problem reported
After entering Printify credentials in the admin, the site didn't fetch/import Printify
products. The owner saw `Shop id: Fabricon`, no clear "Test connection" button, and no way to
turn credentials into products — and did not want to sync via the server.

## 2. Root cause
- **No change-form buttons** — Test connection / sync were Django *changelist* actions
  (dropdown on the list page), invisible on the change form.
- **`shop_id = "Fabricon"`** — a shop *name*, not the numeric Printify shop ID. Requests hit
  `/v1/shops/Fabricon/products.json` and fail.
- **Sync ignored the admin credentials** — `sync_products()` / the daemon `run_tick()` use the
  **env** `PRINTIFY_API_TOKEN` / `PRINTIFY_SHOP_ID`, never the admin-config token. So an
  admin-entered token was never used, and nothing was imported.

## 3. The fix (all from the admin, no server sync)
`shop_id` is **no longer a manual field**. The flow is now button-driven on the change form:

1. Enter **name + API token**, Save.
2. A premium **Printify operations** card appears with **Discover shops** + **Test
   connection** (and, once a shop is selected, **Dry-run catalog sync** + **Sync products
   now**).
3. **Discover shops** → server-side `GET /v1/shops.json` with the decrypted token → an elegant
   list of shops (numeric **ID**, **title**, **sales channel**). A shop whose title matches a
   legacy value like `Fabricon` is flagged **suggested**.
4. **Use this shop** → saves the **numeric** `shop_id` (+ `shop_title`, `shop_sales_channel`,
   `shop_selected_at`) and shows "Shop selected successfully. You can now test connection or
   sync products."
5. **Test connection** → `GET /v1/shops.json`, records `connected/failed` + safe summary.
6. **Sync products now** → `GET /v1/shops/{numeric_id}/products.json` (paginated) using the
   **admin config** credentials, upserting into the local catalogue.

New service functions (`printify_integration/services.py`): `client_for_config(config)`,
`discover_shops(config)`, `import_catalog_from_config(config, apply=)`. They use the config
token+shop_id, never env. Errors are mapped to safe messages (401 invalid token, 403 missing
scopes, 404 bad shop, 429 rate limit, else network) — no payload/token logged.

## 4. `Fabricon` handling
- `shop_id` must be **numeric** (`has_valid_shop()`); a legacy `Fabricon` value is treated as
  invalid and the panel warns: *"'Fabricon' looks like a shop name, not a numeric Printify shop
  ID. Use Discover shops to select the correct shop."*
- During **Discover shops**, a shop titled `Fabricon` is **suggested**, but **Use this shop**
  always saves its **numeric ID** (e.g. `12345678`), never the name.
- Sync refuses to run against a non-numeric shop id with a clear message.

## 5. Catalog import / mapping
Reuses the existing, tested `_upsert_product` mapping: title → name, cleaned description,
price/cost from the enabled variant, category (commercial fallback, never a "Printify"
category), `visible` → available/draft, blueprint/provider ids, tags, options, images
(gallery) and variations (colour/size). **Safety:** a product missing a price, image or
category is imported **hidden** (`is_available=False`) and flagged **to review**. The admin
message reports created / updated / hidden / skipped / errors.

## 6. Dry-run
**Dry-run catalog sync** reads Printify and simulates mapping — it writes **no**
Product/Gallery/Variation — and reports would-create / would-update / missing-price /
missing-image.

## 7. Safety gates (unchanged, enforced)
`allow_product_publish` and `allow_order_creation` stay **OFF** by default and are superadmin-
only. **No publish endpoint and no order endpoint is ever called** (test-asserted). Sync
updates the **local DB only**. All button actions are **POST + superadmin-gated**; a
non-superadmin gets 403. The token is never rendered/logged (only masked last-4 + fingerprint);
`PRINTIFY_CONFIG_KEY` is never shown.

## 8. Permissions
Superadmin: token, discover shops, use shop, test, dry-run, sync. Non-superadmin staff: cannot
discover/select/sync (403) and cannot see the token.

## 9. Migration / deploy
`printify_integration/0006` adds `shop_title`, `shop_sales_channel`, `shop_selected_at`
(editable=False metadata). **Deploy requires `migrate`.** Also `collectstatic` (the ops card
reuses the admin CSS + a new change-form template). No new dependency.

## 10. QA
Tested with a **mocked** Printify client (the owner's real token is never used and no real API
call is made): discover → shop list, use-shop saves numeric id, sync creates + hides
missing-data products, dry-run writes nothing, Fabricon invalid + suggested, token never leaks,
non-superadmin denied, no publish/order endpoint. Browser QA (secret/PII-safe, session-injected
demo shops): the ops card, buttons, warning, shop list and post-selection Sync button all
render; console 0. 2 screenshots in `docs/qa/printify_admin_import/`.

## 11. Troubleshooting
- *"Shop ID must be numeric"* → click Discover shops, then Use this shop.
- *Discover shops failed: Invalid token (401)* → the token is wrong/expired; re-enter it.
- *403 missing scopes* → the token lacks catalog read scope.
- *Nothing imported but 0 errors* → the shop has no products, or all are drafts (imported
  hidden). Check the product admin `?stale_sync=1` / hidden filters.

## 12. Limits
- The daemon `run_tick` still reads the env token (unchanged) — the admin-driven import uses
  the config token; wiring the daemon to the active config is a sensible follow-up.
- Live `Test connection` / `Sync` require a real, valid token on the server; local QA uses
  mocks (never the real token).
