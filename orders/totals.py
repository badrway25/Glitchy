"""
Cart → order money maths, in one place so checkout and place_order agree.

Customer total = items_subtotal + tax + shipping.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from shipping.services import quote_for_cart


@dataclass
class CartTotals:
    quantity: int
    items_subtotal: float
    tax: float
    shipping_cost: float
    grand_total: float
    shipping_quote: object  # ShippingQuote
    currency: str
    shipping_method: str = "standard"
    quote: object = None    # CheckoutQuote — the canonical payload for every surface


def tax_rate() -> float:
    return float(getattr(settings, "STORE_TAX_RATE", 0) or 0)


def compute_cart_totals(cart_items, country: str, *, method="", postal_code="",
                        state="", city="", address1="", address2="", phone="",
                        discount=0.0) -> CartTotals:
    """Cart money for one destination + shipping method.

    Delegates to `shipping.quote.checkout_quote` — the single engine the summary,
    the delivery widget, the order and the payment payloads all share, so the
    number the shopper sees is always the number they are charged. `shipping_quote`
    is kept for callers that still read the old ShippingQuote (PDP copy, order
    snapshot fields)."""
    from shipping.quote import checkout_quote

    quantity = 0
    subtotal = 0.0
    for item in cart_items:
        qty = int(item.quantity or 0)
        quantity += qty
        subtotal += float(item.product.price) * qty

    cq = checkout_quote(cart_items, country=country, method=method,
                        postal_code=postal_code, state=state, city=city,
                        address1=address1, address2=address2, phone=phone,
                        discount=discount)
    legacy_quote = quote_for_cart(country, cart_items, subtotal=subtotal)
    if cq.available:
        # keep the legacy dataclass in step with the canonical numbers
        legacy_quote.cost = cq.shipping_cost
        legacy_quote.free = cq.free
        if cq.delivery_days_min or cq.delivery_days_max:
            legacy_quote.min_days = cq.delivery_days_min
            legacy_quote.max_days = cq.delivery_days_max

    if cq.available:
        tax, shipping_cost, grand_total = cq.tax, cq.shipping_cost, cq.grand_total
    else:
        # The canonical engine only prices the curated country list; the legacy
        # rate table ships anywhere. Falling through to it keeps the pre-existing
        # behaviour for those destinations instead of quietly rendering "Free"
        # (and losing the coupon) on a total we would then charge differently.
        tax = round(subtotal * tax_rate() / 100.0, 2)
        shipping_cost = float(legacy_quote.cost) if legacy_quote.available else 0.0
        grand_total = round(max(0.0, subtotal + tax + shipping_cost
                                - float(discount or 0)), 2)

    return CartTotals(
        quantity=quantity,
        items_subtotal=round(subtotal, 2),
        tax=tax,
        shipping_cost=round(shipping_cost, 2),
        grand_total=round(grand_total, 2),
        shipping_quote=legacy_quote,
        currency=getattr(settings, "STORE_CURRENCY", "EUR"),
        shipping_method=cq.method,
        quote=cq,
    )
