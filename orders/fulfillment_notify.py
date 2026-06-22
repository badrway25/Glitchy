"""Map a Printify fulfillment-status transition to the right order email/n8n event.

Best-effort and idempotent-ish: only fires on a real status change (old != new), never
raises, never blocks the sync, and never invents a tracking number — ORDER_TRACKING is
only sent when a tracking number actually appeared. Emits the event via notify_order_event,
which already degrades to the SMTP fallback when n8n is unavailable.
"""
import logging

logger = logging.getLogger("orders.fulfillment")

# Printify status (lowercased) -> our event constant name.
_IN_PRODUCTION = {"in-production", "in production", "pending", "on-hold"}
_SHIPPED = {"fulfilled", "shipped", "on-the-way", "partially-fulfilled"}


def notify_fulfillment_transition(order, old_status, new_status, *, tracking_added=False):
    try:
        from notifications.notify import notify_order_event
        from notifications import events as ev
    except Exception:
        return

    old_l = (old_status or "").strip().lower()
    new_l = (new_status or "").strip().lower()

    # Tracking became available -> dedicated event (only when a number really exists).
    if tracking_added and getattr(order, "tracking_number", ""):
        _safe(notify_order_event, order, ev.ORDER_TRACKING)

    if new_l == old_l:
        return  # no real transition

    if new_l in _SHIPPED:
        _safe(notify_order_event, order, ev.ORDER_SHIPPED)
    elif new_l in _IN_PRODUCTION:
        _safe(notify_order_event, order, ev.ORDER_IN_PRODUCTION)


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        logger.info("fulfillment notify skipped: %s", exc)
