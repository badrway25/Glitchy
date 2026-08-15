"""Where the shopper's shipping choice lives between requests.

The destination country already had a home (`shipping.geo`, session key
`ship_country`). The chosen *method* had none: the widget rendered radio buttons,
posted nothing back, and `place_order` always charged standard. This module gives
the method the same treatment — one session key, validated on write, read by the
checkout render, the AJAX quote and the order.
"""
from __future__ import annotations

SESSION_KEY = "ship_method"
DEFAULT_METHOD = "standard"

#: methods we are willing to persist (Printify's own vocabulary)
KNOWN_METHODS = ("standard", "priority", "express", "printify_express", "economy")


def get_shipping_method(request, default: str = DEFAULT_METHOD) -> str:
    try:
        value = (request.session.get(SESSION_KEY) or "").strip().lower()
    except Exception:
        return default
    return value if value in KNOWN_METHODS else default


def set_shipping_method(request, method) -> str:
    """Persist a validated method; unknown values reset to standard."""
    value = (str(method or "").strip().lower())
    if value not in KNOWN_METHODS:
        value = DEFAULT_METHOD
    try:
        request.session[SESSION_KEY] = value
        request.session.modified = True
    except Exception:
        pass
    return value


def clear_shipping_method(request) -> None:
    try:
        request.session.pop(SESSION_KEY, None)
        request.session.modified = True
    except Exception:
        pass
