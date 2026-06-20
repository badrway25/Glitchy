"""
Live Printify shipping rates (optional).

Enabled via SHIPPING_USE_PRINTIFY. Fetches the catalog shipping profile for the
first cart item's blueprint/provider and maps the destination country to a cost.
Returns a `shipping.services.ShippingQuote` or None (→ caller uses the fallback).

Results are cached in-process per (blueprint, provider) for the request lifetime
to avoid hammering the API.
"""
from __future__ import annotations

import logging

from django.conf import settings

from shipping.services import ShippingQuote
from .printify_client import get_client

logger = logging.getLogger("printify")

_CACHE: dict = {}


def _shipping_info(blueprint_id, provider_id):
    key = (blueprint_id, provider_id)
    if key in _CACHE:
        return _CACHE[key]
    try:
        data = get_client().get_shipping_info(blueprint_id, provider_id)
    except Exception as exc:
        logger.warning("Printify shipping fetch failed (%s/%s): %s", blueprint_id, provider_id, exc)
        data = None
    _CACHE[key] = data
    return data


def _pick_profile(profiles, country):
    country = (country or "").upper()
    rest = None
    for prof in profiles or []:
        countries = [c.upper() for c in (prof.get("countries") or [])]
        if country in countries:
            return prof
        if "REST_OF_THE_WORLD" in countries:
            rest = prof
    return rest


def printify_cart_quote(country: str, cart_items):
    items = list(cart_items or [])
    if not items:
        return None

    # Use the first item that has Printify blueprint + provider ids.
    product = None
    for it in items:
        p = getattr(it, "product", None)
        if p and p.printify_blueprint_id and p.printify_provider_id:
            product = p
            break
    if product is None:
        return None

    info = _shipping_info(product.printify_blueprint_id, product.printify_provider_id)
    if not info:
        return None

    prof = _pick_profile(info.get("profiles"), country)
    if not prof:
        return None

    qty = sum(int(getattr(it, "quantity", 1) or 1) for it in items)
    first = (prof.get("first_item") or {}).get("cost", 0)
    add = (prof.get("additional_items") or {}).get("cost", 0)
    cost = (float(first) + float(add) * max(0, qty - 1)) / 100.0

    handling = (info.get("handling_time") or {}).get("value", 3)
    try:
        handling = int(handling)
    except (TypeError, ValueError):
        handling = 3
    min_days = handling + 3
    max_days = handling + 8

    currency = getattr(settings, "STORE_CURRENCY", "EUR")
    threshold = float(getattr(settings, "SHIPPING_FREE_THRESHOLD", 0) or 0)
    subtotal = sum(float(getattr(getattr(it, "product", None), "price", 0) or 0) *
                   int(getattr(it, "quantity", 1) or 1) for it in items)
    if threshold and subtotal >= threshold:
        return ShippingQuote(country=country.upper(), cost=0.0, currency=currency,
                             min_days=min_days, max_days=max_days, free=True, source="printify")

    return ShippingQuote(country=country.upper(), cost=round(cost, 2), currency=currency,
                         min_days=min_days, max_days=max_days, source="printify")
