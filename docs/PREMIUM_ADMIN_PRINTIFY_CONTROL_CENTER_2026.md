# Premium Admin + Printify Control Center (2026)

**Branch:** `feature/premium-admin-printify-control-center` (from
`release/staging-printify-fashion-store` @ `14ca5cc`). **New migration + 2 new deps.** No
deploy, no key rotation, Printify push/sync/orders OFF by default.

## 1. Framework — Django Unfold 0.99.0
Chosen after verifying compatibility: Unfold 0.99.0 requires `django>=5.2`, satisfied by the
project's **Django 6.0.1** (pip dry-run resolved cleanly; admin renders 200). Added `unfold`,
`unfold.contrib.filters`, `unfold.contrib.forms` **before** `django.contrib.admin`. Configured
`UNFOLD` with brand identity: title **"Glitchy Commerce Studio"**, subtitle "Print-on-demand
operations", a champagne-gold primary colour ramp, an environment badge (Local/Staging/
Production), and a two-group sidebar (Commerce · Printify control) with icons. Jazzmin/Suit
were not needed; the standard admin + Unfold gives a modern, dark-mode-ready control center
with no template forking of core admin.

## 2. Dashboard (`greatkart/admin_ext.py` + `templates/admin/index.html`)
A "Commerce control center" with real, aggregate KPI cards (no N+1, no PII, no secrets):
- **Catalog:** total, active, Printify, synced, missing-image, missing-price, missing-category,
  stale-sync, sync-errors — each links to the matching product filter.
- **Commerce:** orders, orders (30d), wishlist items.
- **Quick actions:** Printify accounts, Sync monitor, Catalog health, Orders.

## 3. Secure Printify credentials (the security core)
`PrintifyAccountConfig` (migration `0005`) stores the API token **encrypted at rest** with
Fernet (`printify_integration/secrets.py`), keyed by env **`PRINTIFY_CONFIG_KEY`**:
- The token is **write-only**: entered via a `PasswordInput` (`render_value=False`); it is
  **never** stored in plaintext, rendered, or logged. Only a one-way **sha256 fingerprint** +
  **last-4** are shown (e.g. `•••• 7788  fp:e169915f3353`).
- **Fail-closed**: if `PRINTIFY_CONFIG_KEY` is unset, the form refuses to save a token with a
  clear error (env `PRINTIFY_API_TOKEN` still works as a fallback).
- **Permissions**: only a superadmin can enter a token or edit the dangerous switches
  (`sync_mode`, `allow_product_publish`, `allow_order_creation`); ordinary staff see status
  but cannot enter a token — enforced in `get_form` / `get_readonly_fields` / `save_model`.
- **Safe defaults**: `sync_enabled=False`, `allow_product_publish=False`,
  `allow_order_creation=False`, `sync_mode=dry_run`.
- Tests prove the token never appears in the change form, changelist, or history, and that a
  staff POST cannot set/overwrite it.

Generate the key once (never commit it):
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# -> PRINTIFY_CONFIG_KEY=...
```

## 4. Printify admin actions
- **Test connection** (read-only): calls `get_shops` / `list_products(limit=1)` with the
  decrypted token, records `connected/failed` + safe shop name + product count + timestamp.
  Never prints the token, never publishes, never creates an order.
- **Sync now — dry run**: `run_tick(apply=False, force=True)` — reports what *would* sync, no
  writes.
- **Sync now — apply safe** (superadmin only): local catalog update via `sync_products()`.
- The existing `PrintifySyncState` monitor + `SyncLog` remain (backoff, lock, counters).

## 5. Admin-controlled sync (no manual server sync)
`PrintifyAccountConfig` exposes `sync_enabled`, `sync_interval_seconds`, `sync_mode`, and
`is_active`. The systemd timer keeps calling the light `printify_sync_daemon_tick` every ~30s,
but behaviour is governed by the DB config: disabled → exit; no token → safe exit; backoff/
lock respected. (Celery was intentionally **not** introduced.)

## 6. Product admin (`store/admin.py`)
Unfold-styled: **thumbnail** + full-gallery preview, image/variant **counts**, colour-coded
data-quality, sync badges, and **catalog-health filters** — Printify, missing-image,
missing-price, stale-sync (which back the dashboard links). Bulk actions: activate/deactivate,
mark-sync-stale (plus the existing resync/audit/translate). `get_queryset` annotates counts →
**no N+1** in the list.

## 7. Catalog health (`store/management/commands/catalog_health_check.py`)
`python manage.py catalog_health_check --json --safe-output` — reports missing image/price/
category/description, empty gallery, no variants, stale sync, sync errors, duplicate slugs,
active-but-out-of-stock, plus a health score. **Safe output**: counts + slugs only (slugs are
public), no token/PII (test-asserted).

## 8. Orders / customers admin
Unfold-styled OrderAdmin with **cohesive premium KPI cards** (uniform surface; only the value
carries a semantic colour), **soft status pills** (New/Accepted/In production/Completed/
Cancelled), refined margin pills, and PII **masking** (email/name already masked via
`greatkart.pii`). Customers admin inherits Unfold styling.

## 9. Permissions & security summary
- Token + dangerous flags: **superadmin only**. Staff: read status, dry-run.
- Token: encrypted, write-only, never rendered/logged; fingerprint + last-4 only.
- No admin action creates an order, takes payment, or publishes a Printify product (publish is
  double-gated: `allow_product_publish` default off **and** superadmin).
- All safe outputs (health check, connection status, KPIs) carry no token/PII.

## 10. QA
Local admin, 1440 + 390, Unfold light theme, **console 0**. 11 secret/PII-safe screenshots in
`docs/qa/phase68_admin/`. The credential form was verified in the live browser to **not**
contain the real token (only `•••• 7788` + fingerprint).

## 11. Deploy notes
- **New deps**: `pip install django-unfold==0.99.0 cryptography>=42` (in requirements.txt).
- **Migration**: `python manage.py migrate printify_integration` (adds `PrintifyAccountConfig`).
- **New env key**: `PRINTIFY_CONFIG_KEY` (a Fernet key) — required only to store a token from
  the admin; absent → the admin refuses token entry, env token still works.
- `collectstatic` (Unfold assets).
- systemd timer unchanged.

## 12. Limits (honest)
- Drag-and-drop gallery ordering was **not** added (would need a sortable JS lib + an order
  field/migration) — deferred; the existing image inline + big preview cover editing.
- Confirmation pages use Django's standard bulk-action selection; no custom interstitial page
  was added for each action (deferred).
- The dashboard KPI cards are inline-styled (theme-neutral) rather than Unfold component cards,
  to guarantee rendering across Unfold versions.
