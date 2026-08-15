"""Printify Express eligibility — never global, always earned.

Printify Express Delivery (2–3 business days production + delivery) is a
restricted product. Per Printify's official documentation and OpenAPI contract:

* **US mainland only.** Alaska and Hawaii fall back to standard delivery.
* **No PO Box** addresses.
* **Per product AND per variant**: the API exposes `is_printify_express_eligible`
  on both the product and each variant; only eligible ones can ship express.
* **`address_to.email` and `address_to.phone` are required** by the express order
  endpoint (`POST /v1/shops/{shop_id}/orders/express.json`, `shipping_method: 3`).
* It must be chosen **at order placement** — it cannot be added afterwards.

This module answers one question: *may we offer Express for this cart and this
destination?* It returns a list of safe blocker codes (never free text), so the
caller can decide between hiding the option and explaining why. A price is a
separate matter: even with zero blockers, Express is only offered when Printify
actually returned a `printify_express` cost for the cart (see shipping/quote.py).
"""
from __future__ import annotations

import re

from django.conf import settings

# The key Printify uses in POST /orders/shipping.json responses, and the method
# name we persist on the order. `shipping_method: 3` is the API integer.
EXPRESS_METHOD = "printify_express"
EXPRESS_SHIPPING_METHOD_ID = 3

PRIORITY_METHOD = "priority"
PRIORITY_SHIPPING_METHOD_ID = 2
STANDARD_METHOD = "standard"
STANDARD_SHIPPING_METHOD_ID = 1
ECONOMY_METHOD = "economy"
ECONOMY_SHIPPING_METHOD_ID = 4

#: method name -> Printify `shipping_method` integer
SHIPPING_METHOD_IDS = {
    STANDARD_METHOD: STANDARD_SHIPPING_METHOD_ID,
    PRIORITY_METHOD: PRIORITY_SHIPPING_METHOD_ID,
    "express": EXPRESS_SHIPPING_METHOD_ID,
    EXPRESS_METHOD: EXPRESS_SHIPPING_METHOD_ID,
    ECONOMY_METHOD: ECONOMY_SHIPPING_METHOD_ID,
}

#: Express-excluded US states (official: Alaska and Hawaii are standard-only)
EXPRESS_EXCLUDED_STATES = {"AK", "HI"}

_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

# "PO Box 12", "P.O. BOX 4", "post office box 9", "postbus 3" (NL) …
_PO_BOX_RE = re.compile(
    r"(?<![a-z0-9])(p\.?\s*o\.?\s*[-\s]*box|post\s*office\s*box|postbus)(?![a-z])",
    re.IGNORECASE)


def is_po_box(line) -> bool:
    """True when an address line looks like a PO Box (Express is not delivered there)."""
    return bool(_PO_BOX_RE.search(str(line or "")))


def normalize_state(value) -> str:
    """'alaska' / 'AK' / ' Hawaii ' -> 'AK' / 'HI'; unknown values pass through upper-cased."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _US_STATES.get(raw.lower(), raw.upper())


def express_enabled() -> bool:
    """Master switch — Express is opt-in per deployment (default ON, but every
    other rule still has to pass)."""
    return bool(getattr(settings, "SHIPPING_EXPRESS_ENABLED", True))


def destination_allows_express(country, *, state="", address1="", address2=""):
    """(allowed, reason). Reason is a safe code, '' when allowed."""
    if (str(country or "").strip().upper() != "US"):
        return False, "destination_not_supported"
    if normalize_state(state) in EXPRESS_EXCLUDED_STATES:
        return False, "destination_not_supported"
    if is_po_box(address1) or is_po_box(address2):
        return False, "po_box"
    return True, ""


def _variant_rows(item):
    getter = getattr(item, "variations", None)
    if getter is None:
        return []
    try:
        return list(getter.all())
    except Exception:
        return []


def item_is_express_eligible(item) -> bool:
    """A line qualifies only when its product AND every chosen variant that
    carries eligibility data are flagged eligible by Printify."""
    product = getattr(item, "product", None)
    if product is None or not getattr(product, "printify_express_eligible", False):
        return False
    for variation in _variant_rows(item):
        if getattr(variation, "printify_express_eligible", True) is False:
            return False
    return True


def express_blockers(cart_items, *, country, state="", address1="", address2="",
                     phone="", email=None):
    """Safe codes explaining why Express cannot be offered ([] when it can).

    Codes: express_disabled, destination_not_supported, po_box, phone_required,
    email_required, items_not_eligible, empty_cart.
    """
    blockers = []
    if not express_enabled():
        blockers.append("express_disabled")

    items = list(cart_items or [])
    if not items:
        blockers.append("empty_cart")

    allowed, reason = destination_allows_express(
        country, state=state, address1=address1, address2=address2)
    if not allowed:
        blockers.append(reason)

    # The express endpoint requires both on address_to.
    if not str(phone or "").strip():
        blockers.append("phone_required")
    if email is not None and not str(email or "").strip():
        blockers.append("email_required")

    if items and not all(item_is_express_eligible(it) for it in items):
        blockers.append("items_not_eligible")

    return blockers


def express_eligible_item_count(cart_items) -> int:
    return sum(1 for it in (cart_items or []) if item_is_express_eligible(it))


def shipping_method_id(method) -> int:
    """Printify `shipping_method` integer for a method name (defaults to standard)."""
    return SHIPPING_METHOD_IDS.get(str(method or "").strip().lower(),
                                   STANDARD_SHIPPING_METHOD_ID)


def is_express(method) -> bool:
    return str(method or "").strip().lower() in (EXPRESS_METHOD, "express")
