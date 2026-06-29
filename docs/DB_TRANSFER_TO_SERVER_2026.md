# Database transfer to the server — safe, professional procedure (2026)

**Golden rules (non-negotiable):**
1. **Back up the server DB before any write.** No backup → no import.
2. **Never overwrite production data without explicit owner authorization.**
3. **Dry-run / compare counts** before and after.
4. Prefer importing **catalog/products/Printify/shipping** data; **do NOT import real
   user accounts, orders, addresses or payment data** unless the owner explicitly
   authorizes it (PII + legal). When in doubt, ask.
5. **No secrets in any dump that leaves the box**; never commit a dump to git
   (`*.sql`, `*.dump`, `*.sqlite3` are ignored).

The dev database today is **SQLite**; staging/production is **PostgreSQL**. So a
transfer is also an engine migration — do it via Django fixtures (per-model), not a
raw file copy.

---

## 0. Audit both sides first (no PII, masked db name)
```bash
python manage.py db_readiness_audit            # human
python manage.py db_readiness_audit --json     # machine (counts only)
```
Run it on **source** and **server** and compare the counts. Keep the JSON in the
change log. Example (counts only): products, categories, users, orders,
printify_products, shipping_profiles, translations + migration applied/pending.

## 1. Back up the SERVER database (always, first)
```bash
# Postgres (server)
TS=$(date +%Y%m%d_%H%M%S)
pg_dump "$DATABASE_URL" -Fc -f /var/backups/glitchy/db_$TS.dump
ls -lh /var/backups/glitchy/db_$TS.dump        # verify size > 0
# (optional) verify it restores into a scratch db before proceeding
```
Store the backup off the app server. **Do not commit it.**

## 2. Export the SOURCE data (catalog-only is the default, PII-free)
Export only the safe, catalog-side models (no users/orders/addresses):
```bash
python manage.py dumpdata \
  category.Category \
  store.Product store.Variation store.ProductGallery \
  store.ProductDescriptionTranslation \
  printify_integration.PrintifyShippingProfile \
  printify_integration.PrintifyPrintArea \
  --indent 2 --natural-foreign --natural-primary \
  -o /tmp/glitchy_catalog_$TS.json
```
> Full-DB export (incl. users/orders) requires **explicit owner authorization**.
> If authorized, add `auth.User`, `orders.*`, `accounts.*` and treat the file as PII:
> encrypt at rest, transfer over SSH only, delete after import, never commit.

## 3. Dry-run / validate the export
```bash
python -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d),'objects'); \
print(sorted({o['model'] for o in d}))" /tmp/glitchy_catalog_$TS.json
```
Confirm the model set is exactly what you intend (no `auth.user`, no `orders.order`
unless authorized).

## 4. Import on the SERVER (after backup, into a migrated schema)
```bash
# schema first (idempotent)
python manage.py migrate --noinput              # applies 0003 (phase 51) + 0004 (sync state)
# load the catalog fixture
python manage.py loaddata /tmp/glitchy_catalog_$TS.json
# refresh static + smoke
python manage.py collectstatic --noinput
python manage.py db_readiness_audit             # compare counts vs source
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/        # expect 200
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/store/  # expect 200
```
`loaddata` **upserts by pk** — it does not delete server rows it doesn't mention.
It will overwrite rows with matching pks, so only run it when you intend the source
catalog to win. If unsure, import into a **staging** DB first and diff.

## 5. Rollback
```bash
# stop traffic / put up maintenance, then restore the pre-import backup
sudo systemctl stop glitchy
dropdb glitchy && createdb glitchy            # or restore into the same db
pg_restore -d "$DATABASE_URL" --clean --if-exists /var/backups/glitchy/db_$TS.dump
python manage.py migrate --noinput
sudo systemctl start glitchy
python manage.py db_readiness_audit           # verify counts match the backup
```

## 6. Data policy summary
| Data | Default | Requires explicit authorization |
|---|---|---|
| Categories, Products, Variations, Gallery, Translations | ✅ import | — |
| Printify shipping profiles / print areas | ✅ import | — |
| **Users / accounts** | ❌ skip | ✅ owner sign-off (PII) |
| **Orders / order products** | ❌ skip | ✅ owner sign-off (PII + financial) |
| **Addresses / payment** | ❌ never | ✅ + legal review |

## 7. After transfer — Printify
The catalog you imported may have stale variants/prices. Run the **manual** full
sync once (read-only), then let the light 30s tick keep things fresh:
```bash
python manage.py printify_sync_products        # manual discovery (read-only)
python manage.py printify_sync_status          # confirm stale count drops
```
See `docs/PRINTIFY_PRODUCTION_SYNC_30S_2026.md`. No orders are created; nothing is
published (`PRINTIFY_PUSH_ENABLED=False`).
