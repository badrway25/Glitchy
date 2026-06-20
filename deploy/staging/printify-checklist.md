# Printify — Staging Runbook (PUSH DISABLED)

**Mandatory in staging:** `PRINTIFY_PUSH_ENABLED=False`. No real Printify orders
are created. `rotate_secrets_check.sh` enforces this.

## 1. Connectivity + catalog
```bash
./env/bin/python manage.py printify_check            # lists the shop(s)
./env/bin/python manage.py printify_sync_products --limit 50
```
Verifies products, variants (color/size), images, and per-variant **production cost**
(`base_cost` / `Variation.production_cost`). Shipping profiles are used when
`SHIPPING_USE_PRINTIFY=True` (else the fallback rate table applies).

## 2. Costs / margins for historical orders
```bash
./env/bin/python manage.py backfill_order_costs --dry-run   # preview
./env/bin/python manage.py backfill_order_costs             # apply (real data only)
```
Production cost is backfilled **only** from synced product/variant data — never
fabricated. Orders with no Printify match keep cost 0.

## 3. Order status / tracking
```bash
./env/bin/python manage.py printify_pull_orders --limit 20
```
(Schedule via systemd timer / cron — see `systemd-timers.example`.)

## 4. Observability
- Admin → **Printify sync logs**: kind, status (ok/partial/error), counts, duration.
- Product admin: per-product sync status + "Resync from Printify" action.

## 5. Meaning of `printify_status=push_disabled`
The order was finalized (costs/margins computed, customer emailed via n8n) but the
order was **not** sent to Printify because `PRINTIFY_PUSH_ENABLED=False`. Expected
in staging.

## 6. Conditions to set `PRINTIFY_PUSH_ENABLED=True` (PRODUCTION ONLY)
ALL must hold, with **explicit authorization**:
1. Staging fully green (smoke + e2e order).
2. n8n real email send/receive tested.
3. Stripe public webhook tested end-to-end (live or test as agreed).
4. One controlled test order reviewed (and, if needed, cancelled in Printify).
5. Sufficient Printify balance / payment method configured.

Until then, leave it **False**.
