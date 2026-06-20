"""
Shipping estimation.

Strategy:
    1. If a Printify-backed rate is available for the cart (and enabled), use it.
    2. Otherwise fall back to the configurable rate table in settings.

Everything here is deterministic and unit-testable; the Printify hook degrades
gracefully to the fallback when data is missing or the API is unreachable.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from django.conf import settings
from django.utils.translation import gettext_lazy as _


@dataclass
class ShippingQuote:
    country: str
    cost: float                 # what the customer pays
    currency: str
    min_days: int
    max_days: int
    free: bool = False
    available: bool = True
    source: str = "fallback"    # "fallback" | "printify" | "free"
    message: str = ""

    def as_dict(self) -> dict:
        data = asdict(self)
        data["eta_label"] = self.eta_label
        return data

    @property
    def eta_label(self) -> str:
        if not self.available:
            return ""
        if self.min_days == self.max_days:
            return _("%(d)d business days") % {"d": self.max_days}
        return _("%(a)d–%(b)d business days") % {"a": self.min_days, "b": self.max_days}


def _rate_for(country: str) -> dict:
    table = getattr(settings, "SHIPPING_FALLBACK_RATES", {}) or {}
    return table.get((country or "").upper(), getattr(settings, "SHIPPING_DEFAULT_RATE", {
        "first": 9.90, "additional": 3.0, "min_days": 7, "max_days": 15,
    }))


def is_country_supported(country: str) -> bool:
    supported = getattr(settings, "SHIPPING_SUPPORTED_COUNTRIES", []) or []
    if not supported:
        return True  # empty => ship anywhere
    return (country or "").upper() in {c.upper() for c in supported}


def fallback_quote(country: str, total_quantity: int, subtotal: float) -> ShippingQuote:
    """Pure fallback computation from the settings rate table."""
    country = (country or getattr(settings, "SHIPPING_DEFAULT_COUNTRY", "IT")).upper()
    currency = getattr(settings, "STORE_CURRENCY", "EUR")

    if not is_country_supported(country):
        return ShippingQuote(
            country=country, cost=0.0, currency=currency, min_days=0, max_days=0,
            available=False, source="fallback",
            message=str(_("We do not ship to this country yet.")),
        )

    rate = _rate_for(country)
    qty = max(1, int(total_quantity or 1))
    cost = float(rate["first"]) + float(rate["additional"]) * (qty - 1)

    threshold = float(getattr(settings, "SHIPPING_FREE_THRESHOLD", 0) or 0)
    if threshold and float(subtotal or 0) >= threshold:
        return ShippingQuote(
            country=country, cost=0.0, currency=currency,
            min_days=int(rate["min_days"]), max_days=int(rate["max_days"]),
            free=True, source="free",
            message=str(_("Free shipping")),
        )

    return ShippingQuote(
        country=country, cost=round(cost, 2), currency=currency,
        min_days=int(rate["min_days"]), max_days=int(rate["max_days"]),
        source="fallback",
    )


def quote_for_cart(country: str, cart_items, subtotal: float | None = None) -> ShippingQuote:
    """
    Estimate shipping for a cart (any iterable of objects exposing `.quantity`).

    Tries Printify first when enabled, then falls back to the rate table.
    """
    total_qty = 0
    computed_subtotal = 0.0
    for item in cart_items or []:
        qty = int(getattr(item, "quantity", 1) or 1)
        total_qty += qty
        price = getattr(getattr(item, "product", None), "price", 0) or 0
        computed_subtotal += float(price) * qty
    if subtotal is None:
        subtotal = computed_subtotal
    total_qty = total_qty or 1

    # Printify hook (degrades to fallback on any problem)
    if getattr(settings, "SHIPPING_USE_PRINTIFY", False):
        try:
            from printify_integration.shipping import printify_cart_quote

            pq = printify_cart_quote(country, cart_items)
            if pq is not None:
                return pq
        except Exception:
            pass

    return fallback_quote(country, total_qty, subtotal)
