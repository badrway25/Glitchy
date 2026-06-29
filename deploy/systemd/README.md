# Glitchy systemd units — production-safe Printify sync

These are **templates** (documented, not auto-installed). They run the *light* sync
tick every ~30s. The cadence is safe **only** because each tick is self-limiting.

## What the tick does (and never does)
- Re-syncs a **tiny batch of stale products** (`PRINTIFY_SYNC_BATCH_SIZE`, default 2)
  via a read-only `GET` + a local upsert. Capped by `PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK`.
- Holds a **DB lock** so ticks never overlap; enters a **persisted exponential
  backoff** after `429`/`5xx` and skips until it clears.
- Exits immediately when there is nothing stale, when locked, when in backoff, or
  when `PRINTIFY_SYNC_ENABLED` is not true.
- **Never** creates orders. **Never** publishes products (also gated by the separate
  `PRINTIFY_PUSH_ENABLED`). Logs no token, no PII, no raw payload.

## Required env (`/etc/glitchy/env`, never in git)
```
PRINTIFY_SYNC_ENABLED=True          # off by default; this turns the tick on
PRINTIFY_API_TOKEN=...              # rotated token
PRINTIFY_SHOP_ID=...
# optional tuning (defaults shown)
PRINTIFY_SYNC_BATCH_SIZE=2
PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK=5
PRINTIFY_SYNC_BACKOFF_SECONDS=60
PRINTIFY_SYNC_STALE_AFTER_MINUTES=360
PRINTIFY_PUSH_ENABLED=False         # keep False; publishing stays disabled
```

## Install
```bash
sudo cp deploy/systemd/glitchy-printify-sync.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now glitchy-printify-sync.timer
systemctl list-timers glitchy-printify-sync.timer   # verify next run
journalctl -u glitchy-printify-sync.service -n 20    # compact JSON per tick
python manage.py printify_sync_status                # monitor (no secrets)
```

Disable instantly: `sudo systemctl disable --now glitchy-printify-sync.timer`
(or set `PRINTIFY_SYNC_ENABLED=False` and the ticks become no-ops).

## Full discovery sync & shipping profiles (separate, less frequent)
The 30s tick is intentionally light and does **not** do heavy discovery. Run those
manually or on a slow timer (e.g. daily), never every 30s:
```bash
python manage.py printify_sync_products              # discover new products (manual)
python manage.py printify_sync_shipping_profiles     # shipping rates (e.g. daily)
```
For a daily shipping-profile timer, clone the units above with
`OnCalendar=daily` instead of `OnUnitActiveSec=30s` and the appropriate `ExecStart`.
