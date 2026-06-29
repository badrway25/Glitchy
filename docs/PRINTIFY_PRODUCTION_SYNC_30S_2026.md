# Printify production sync — safe 30-second tick (2026)

A production-safe way to keep the catalog fresh against Printify **without** hitting
rate limits, overlapping, creating orders, or publishing products.

## Why a 30s tick is safe (it's not a full sync)
The owner asked for a 30-second cadence. A heavy full sync every 30s would blow
Printify's rate limits. Instead, each tick is **light and self-limiting**:

- Re-syncs only a **tiny batch of stale products** (`PRINTIFY_SYNC_BATCH_SIZE`,
  default **2**) — each is a single read-only `GET /products/{id}` + a local upsert.
- Capped by `PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK` (default **5**).
- A **DB-backed lock** (`PrintifySyncState`, race-safe conditional UPDATE) prevents
  overlapping ticks across separate systemd one-shot processes.
- A **persisted exponential backoff** after any `429`/`5xx` makes subsequent ticks
  no-op until the window clears (the client also retries once and honours `Retry-After`).
- Exits immediately when nothing is stale, when locked, when in backoff, when no
  token, or when `PRINTIFY_SYNC_ENABLED` is false.

So a tick that finds nothing to do is essentially free, and the worst case per tick
is a handful of read-only GETs.

## What it does — and never does
| Does | Never does |
|---|---|
| `GET /products/{id}` (read-only) | Create an order |
| Local upsert of product/variant/cost data | Send to production / publish |
| Update `printify_synced_at` / status | Push when `PRINTIFY_PUSH_ENABLED=False` |
| Persist counters + backoff (monitoring) | Log token / PII / raw payload |

The tick code path contains **no** call to `create_order` or `send_to_production`.
Publishing is independently gated by the separate `PRINTIFY_PUSH_ENABLED` (kept False).

## Commands
```bash
# safe dry run (default): report what WOULD sync, no network
python manage.py printify_sync_daemon_tick

# production (what the timer runs): execute against the live API
python manage.py printify_sync_daemon_tick --apply --live --safe-output

# monitor (no secrets)
python manage.py printify_sync_status            # human
python manage.py printify_sync_status --json     # machine

# manual full discovery sync (heavy — NOT every 30s)
python manage.py printify_sync_products
python manage.py printify_sync_shipping_profiles  # separate, e.g. daily
```
Tick JSON / status JSON contain only safe fields (`token_present` is a boolean, the
token value is never emitted).

## Settings (env, all safe defaults; OFF unless explicitly enabled)
```
PRINTIFY_SYNC_ENABLED=False             # master switch (set True on the server only)
PRINTIFY_SYNC_INTERVAL_SECONDS=30       # display/monitor; the real cadence is the timer
PRINTIFY_SYNC_BATCH_SIZE=2
PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK=5
PRINTIFY_SYNC_BACKOFF_SECONDS=60        # base; doubles each consecutive 429/5xx
PRINTIFY_SYNC_STALE_AFTER_MINUTES=360   # a product is "stale" after 6h
PRINTIFY_SYNC_FULL_INTERVAL_MINUTES=1440
PRINTIFY_SYNC_LOCK_TIMEOUT_SECONDS=120  # stale-lock takeover guard
PRINTIFY_PUSH_ENABLED=False             # separate; keep False
```

## systemd (30s timer)
Templates live in `deploy/systemd/` (documented, not auto-installed):
`glitchy-printify-sync.service` (oneshot `--apply --live --safe-output`) +
`glitchy-printify-sync.timer` (`OnUnitActiveSec=30s`). Install + activation:
see `deploy/systemd/README.md`. Activation requires `PRINTIFY_SYNC_ENABLED=True`
in `/etc/glitchy/env`; disable instantly with `systemctl disable --now` or by
flipping the env back to False.

## Monitoring
`python manage.py printify_sync_status` and the read-only **Printify sync state**
admin show: enabled, token present, stale count, products synced total, last tick
(synced/requests), last full sync, lock state, backoff active/until, consecutive
errors, last error status. No token is shown.

## Honest limits
- The light tick re-syncs **stale local products**; **discovery of brand-new** shop
  products is the **manual** full sync (kept out of the 30s tick by design).
- `_upsert_product` runs with `refresh_images=False`, so it won't re-download images
  for already-synced products; a never-synced product with missing images may fetch
  them once (still bounded by the per-tick product budget).
- Live mode requires a **rotated** `PRINTIFY_API_TOKEN`; today the rotation gate is
  still red, so production stays in dry-run until the key is rotated.
