"""Production-safe Printify sync — the light tick run every ~30s by a systemd timer.

Design goals (per owner brief, Printify rate limits in mind):
  * LIGHT: re-sync only a tiny batch of *stale* local Printify products per tick
    (each = a single read-only GET + a local upsert). Capped request budget.
  * SAFE: DB-backed lock (no overlapping ticks), persisted exponential backoff on
    429/5xx, fail-fast client (max_retries=1) so a tick never blocks for long.
  * READ-ONLY against Printify: it calls ONLY get_product. It NEVER creates orders
    and NEVER publishes products (there is no such code path here; publishing also
    stays gated behind the separate PRINTIFY_PUSH_ENABLED).
  * OFF by default: does nothing unless PRINTIFY_SYNC_ENABLED is true AND --apply
    --live are passed (the daemon passes both; bare invocation is a dry run).

Returns a JSON-safe dict with NO token, NO PII, NO raw payload.
"""
from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from store.models import Product
from .models import PrintifySyncState
from .printify_client import PrintifyClient, PrintifyError

logger = logging.getLogger("printify")


@dataclass
class TickConfig:
    enabled: bool = False
    batch_size: int = 2
    max_requests: int = 5
    backoff_seconds: int = 60
    stale_after_minutes: int = 360
    lock_timeout_seconds: int = 120
    apply: bool = False      # actually write (else pure report)
    live: bool = False       # call the real API (else no network)
    force: bool = False      # ignore the enabled gate (manual one-off)

    @classmethod
    def from_settings(cls, **overrides):
        cfg = cls(
            enabled=bool(getattr(settings, "PRINTIFY_SYNC_ENABLED", False)),
            batch_size=int(getattr(settings, "PRINTIFY_SYNC_BATCH_SIZE", 2)),
            max_requests=int(getattr(settings, "PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK", 5)),
            backoff_seconds=int(getattr(settings, "PRINTIFY_SYNC_BACKOFF_SECONDS", 60)),
            stale_after_minutes=int(getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360)),
            lock_timeout_seconds=int(getattr(settings, "PRINTIFY_SYNC_LOCK_TIMEOUT_SECONDS", 120)),
        )
        for k, v in overrides.items():
            if v is not None and hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


@dataclass
class TickResult:
    ok: bool = True
    action: str = "skipped"          # "skipped" | "synced"
    reason: str = ""                 # disabled|locked|backoff|nothing_stale|dry_run|no_token|done|error
    enabled: bool = False
    live: bool = False
    apply: bool = False
    stale_total: int = 0
    selected: int = 0
    synced: int = 0
    errors: int = 0
    requests_used: int = 0
    backoff_active: bool = False
    backoff_until: str | None = None
    products_synced_total: int = 0
    messages: list = field(default_factory=list)

    def as_dict(self):
        return {
            "ok": self.ok, "action": self.action, "reason": self.reason,
            "enabled": self.enabled, "live": self.live, "apply": self.apply,
            "stale_total": self.stale_total, "selected": self.selected,
            "synced": self.synced, "errors": self.errors,
            "requests_used": self.requests_used,
            "backoff_active": self.backoff_active, "backoff_until": self.backoff_until,
            "products_synced_total": self.products_synced_total,
            "messages": self.messages,
        }


def _stale_qs(stale_after_minutes, now):
    cutoff = now - timezone.timedelta(minutes=stale_after_minutes)
    return (Product.objects
            .filter(printify_product_id__isnull=False)
            .exclude(printify_product_id="")
            .filter(Q(printify_sync_status=Product.SYNC_NOT_SYNCED)
                    | Q(printify_synced_at__isnull=True)
                    | Q(printify_synced_at__lt=cutoff))
            .order_by(F("printify_synced_at").asc(nulls_first=True)))


def _safe_err(exc) -> str:
    """A short, token/PII-free error label (never the raw payload)."""
    status = getattr(exc, "status", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


def run_tick(*, apply=False, live=False, force=False, batch_size=None,
             max_requests=None, client=None) -> TickResult:
    """Run one production-safe sync tick. Pure function over the DB + (optionally)
    the Printify API. Acquires the lock, respects backoff, syncs a small stale batch."""
    now = timezone.now()
    cfg = TickConfig.from_settings(batch_size=batch_size, max_requests=max_requests)
    cfg.apply, cfg.live, cfg.force = apply, live, force
    res = TickResult(enabled=cfg.enabled, live=cfg.live, apply=cfg.apply)

    # 1) enabled gate (unless explicitly forced for a manual one-off)
    if not cfg.enabled and not cfg.force:
        res.reason = "disabled"
        res.messages.append("PRINTIFY_SYNC_ENABLED is false; nothing to do.")
        return res

    # 2) lock (race-safe); if not won, another tick is running → exit cleanly
    owner = f"{socket.gethostname()[:60]}:{_pid()}"
    if not PrintifySyncState.try_acquire(owner, cfg.lock_timeout_seconds, now=now):
        res.reason = "locked"
        res.messages.append("Another sync tick holds the lock; skipping (no overlap).")
        return res

    try:
        state = PrintifySyncState.load()
        res.products_synced_total = state.products_synced_total

        # 3) backoff window after a recent 429/5xx
        if state.in_backoff(now=now):
            res.reason = "backoff"
            res.backoff_active = True
            res.backoff_until = state.backoff_until.isoformat() if state.backoff_until else None
            res.messages.append("In backoff window after a recent rate-limit/5xx; skipping.")
            _stamp_tick(state, now, synced=0, requests=0)
            return res

        # 4) find stale products
        stale = _stale_qs(cfg.stale_after_minutes, now)
        res.stale_total = stale.count()
        if res.stale_total == 0:
            res.reason = "nothing_stale"
            res.messages.append("No stale Printify products; tick is a no-op.")
            _stamp_tick(state, now, synced=0, requests=0)
            return res

        budget = max(1, min(cfg.batch_size, cfg.max_requests))
        batch = list(stale[:budget])
        res.selected = len(batch)

        # 5) dry run (default) or no live → report only, no network
        token = getattr(settings, "PRINTIFY_API_TOKEN", "")
        if not cfg.apply or not cfg.live:
            res.reason = "dry_run"
            res.messages.append(
                f"DRY RUN: would re-sync {res.selected} stale product(s) "
                f"(of {res.stale_total}). Pass --apply --live to execute.")
            _stamp_tick(state, now, synced=0, requests=0)
            return res
        if not token:
            res.reason = "no_token"
            res.messages.append("Live requested but PRINTIFY_API_TOKEN is empty; skipping.")
            _stamp_tick(state, now, synced=0, requests=0)
            return res

        # 6) live, apply: re-sync the small batch (read-only GET + local upsert)
        synced, errors, requests_used, rate_limited = _resync_batch(batch, state, cfg, now, client)
        res.synced, res.errors, res.requests_used = synced, errors, requests_used

        if rate_limited:
            res.reason = "backoff"
            res.backoff_active = True
            res.backoff_until = state.backoff_until.isoformat() if state.backoff_until else None
            res.messages.append("Hit a rate-limit/5xx; entered backoff and stopped early.")
        else:
            if synced and not errors:
                state.clear_backoff()
            res.reason = "done"
            res.action = "synced" if synced else "skipped"
            res.messages.append(f"Re-synced {synced} product(s), {errors} error(s).")

        # The DB lock serialises ticks, so a plain increment is race-free.
        state.products_synced_total = (state.products_synced_total or 0) + synced
        _stamp_tick(state, now, synced=synced, requests=requests_used)
        res.products_synced_total = state.products_synced_total
        return res
    except Exception as exc:  # never let a tick crash the timer
        res.ok = False
        res.reason = "error"
        res.errors += 1
        res.messages.append(f"Tick error: {_safe_err(exc)}")
        logger.warning("Printify sync tick error: %s", _safe_err(exc))
        return res
    finally:
        PrintifySyncState.release(owner)


def _resync_batch(batch, state, cfg, now, client=None):
    """Re-sync each product via a single read-only GET + local upsert. Returns
    (synced, errors, requests_used, rate_limited). Stops on the first 429/5xx and
    enters a persisted backoff window."""
    from .services import _upsert_product, _resolve_fallback_category

    # Fail-fast client (one quick retry); rely on tick-level persisted backoff.
    client = client or PrintifyClient(
        token=getattr(settings, "PRINTIFY_API_TOKEN", ""),
        shop_id=getattr(settings, "PRINTIFY_SHOP_ID", ""),
        timeout=20, max_retries=1)
    settings_map = getattr(settings, "PRINTIFY_BLUEPRINT_CATEGORY_MAP", {}) or {}
    fallback = _resolve_fallback_category()

    synced = errors = requests_used = 0
    for product in batch:
        if requests_used >= cfg.max_requests:
            break
        requests_used += 1  # count the attempt — it hits the network regardless of outcome
        try:
            payload = client.get_product(product.printify_product_id)  # read-only GET
            _upsert_product(payload, fallback, settings_map, False, refresh_images=False)
            synced += 1
        except PrintifyError as exc:
            errors += 1
            status = getattr(exc, "status", None)
            _mark_product_error(product, exc)
            if status == 429 or (status and status >= 500):
                wait = state.enter_backoff(cfg.backoff_seconds, status=status, now=now)
                logger.warning("Printify sync backoff %ss after HTTP %s", wait, status)
                return synced, errors, requests_used, True
        except Exception as exc:  # unexpected, non-API error: skip this product
            errors += 1
            _mark_product_error(product, exc)
    return synced, errors, requests_used, False


def _mark_product_error(product, exc):
    try:
        product.printify_sync_status = Product.SYNC_ERROR
        product.printify_sync_error = _safe_err(exc)[:1000]
        product.save(update_fields=["printify_sync_status", "printify_sync_error"])
    except Exception:
        pass


def _stamp_tick(state, now, *, synced, requests):
    state.last_tick_at = now
    state.last_tick_synced = synced
    state.last_tick_requests = requests
    state.save(update_fields=["last_tick_at", "last_tick_synced", "last_tick_requests",
                              "products_synced_total", "backoff_until", "backoff_level",
                              "consecutive_errors", "last_error_at", "last_error_status",
                              "updated_at"])


def _pid():
    import os
    return os.getpid()


def status_snapshot() -> dict:
    """A JSON-safe monitoring snapshot (no token, no PII)."""
    now = timezone.now()
    state = PrintifySyncState.load()
    stale_total = _stale_qs(int(getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360)),
                            now).count()
    return {
        "enabled": bool(getattr(settings, "PRINTIFY_SYNC_ENABLED", False)),
        "push_enabled": bool(getattr(settings, "PRINTIFY_PUSH_ENABLED", False)),
        "interval_seconds": int(getattr(settings, "PRINTIFY_SYNC_INTERVAL_SECONDS", 30)),
        "batch_size": int(getattr(settings, "PRINTIFY_SYNC_BATCH_SIZE", 2)),
        "max_requests_per_tick": int(getattr(settings, "PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK", 5)),
        "token_present": bool(getattr(settings, "PRINTIFY_API_TOKEN", "")),
        "stale_products": stale_total,
        "products_synced_total": state.products_synced_total,
        "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else None,
        "last_tick_synced": state.last_tick_synced,
        "last_tick_requests": state.last_tick_requests,
        "last_full_sync_at": state.last_full_sync_at.isoformat() if state.last_full_sync_at else None,
        "locked": bool(state.locked_at),
        "backoff_active": state.in_backoff(now=now),
        "backoff_until": state.backoff_until.isoformat() if state.backoff_until else None,
        "backoff_level": state.backoff_level,
        "consecutive_errors": state.consecutive_errors,
        "last_error_status": state.last_error_status,
        "last_error_at": state.last_error_at.isoformat() if state.last_error_at else None,
    }
