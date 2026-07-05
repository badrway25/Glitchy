"""Honest order timeline — every step is derived from REAL data, never invented.

Sources of truth:
- payment  → Order.is_ordered + Payment
- Printify → Order.printify_order_id / printify_status / printify_last_error
- shipping → Order.tracking_number / tracking_url / carrier (set only by real syncs)

The old template inferred "Packed/Shipped" from Order.status, which finalize sets to
"Accepted" immediately after payment — so the page showed production progress that had
never happened. This module only ever marks a step done/current when the backing field
proves it; everything else stays pending with truthful copy.
"""
from django.utils.translation import gettext_lazy as _

# Printify order statuses that mean "the factory is working on it" (public API values).
_PRODUCTION_STATUSES = {"in-production", "in_production", "inproduction"}
_SHIPPED_STATUSES = {"shipped", "fulfilled", "partially-fulfilled"}
_DELIVERED_STATUSES = {"delivered"}
_ERROR_STATUSES = {"canceled", "cancelled", "payment-not-received", "on-hold", "has-issues"}


def get_order_timeline(order):
    """List of steps: {key, label, description, icon, status, action_url}.

    status ∈ done | current | pending | error. Exactly one step is `current`
    (the first not-done one) unless an error state takes over.
    """
    p_status = (order.printify_status or "").strip().lower()
    has_printify = bool(order.printify_order_id)
    has_tracking = bool(order.tracking_number or order.tracking_url)
    shipped = has_tracking or p_status in _SHIPPED_STATUSES
    delivered = p_status in _DELIVERED_STATUSES
    in_production = p_status in _PRODUCTION_STATUSES or shipped or delivered
    printify_error = p_status in _ERROR_STATUSES or bool(order.printify_last_error and not has_printify)

    steps = [
        {
            "key": "payment",
            "label": _("Payment confirmed"),
            "description": _("Your payment was verified and your order is locked in."),
            "icon": "fa-check-circle",
            "done": bool(order.is_ordered),
        },
        {
            "key": "printify",
            "label": _("Sent to production"),
            "description": (_("Your order has been handed to our production partner.")
                            if has_printify else
                            _("Production sync pending — this page updates as production "
                              "information becomes available.")),
            "icon": "fa-industry",
            "done": has_printify,
            "error": printify_error and not has_printify,
        },
        {
            "key": "production",
            "label": _("In production"),
            "description": (_("Your items are being printed and quality-checked.")
                            if in_production else
                            _("Production starts after the order is accepted by the factory.")),
            "icon": "fa-print",
            "done": in_production,
        },
        {
            "key": "shipped",
            "label": _("Shipped"),
            "description": (_("Your parcel is with the carrier.") if shipped else
                            _("Tracking will appear when the carrier receives the parcel.")),
            "icon": "fa-truck",
            "done": shipped,
            "action_url": order.tracking_url or "",
        },
        {
            "key": "delivered",
            "label": _("Delivered"),
            "description": (_("Enjoy!") if delivered else
                            _("Marked automatically once the carrier confirms delivery.")),
            "icon": "fa-box-open",
            "done": delivered,
        },
    ]

    current_assigned = False
    for s in steps:
        if s.pop("error", False):
            s["status"] = "error"
            current_assigned = True
        elif s.pop("done"):
            s["status"] = "done"
        elif not current_assigned:
            s["status"] = "current"
            current_assigned = True
        else:
            s["status"] = "pending"
        s["label"] = str(s["label"])
        s["description"] = str(s["description"])
    return steps


def timeline_summary(order):
    """Compact production status key for JSON/status chips."""
    p = (order.printify_status or "").strip().lower()
    if p in _DELIVERED_STATUSES:
        return "delivered"
    if order.tracking_number or order.tracking_url or p in _SHIPPED_STATUSES:
        return "shipped"
    if p in _PRODUCTION_STATUSES:
        return "in_production"
    if order.printify_order_id:
        return "sent_to_printify"
    if p in _ERROR_STATUSES or order.printify_last_error:
        return "sync_error"
    return "sync_pending"
