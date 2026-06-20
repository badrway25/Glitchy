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


def tax_rate() -> float:
    return float(getattr(settings, "STORE_TAX_RATE", 0) or 0)


def compute_cart_totals(cart_items, country: str) -> CartTotals:
    quantity = 0
    subtotal = 0.0
    for item in cart_items:
        qty = int(item.quantity or 0)
        quantity += qty
        subtotal += float(item.product.price) * qty

    quote = quote_for_cart(country, cart_items, subtotal=subtotal)
    shipping_cost = float(quote.cost) if quote.available else 0.0

    tax = round(subtotal * tax_rate() / 100.0, 2)
    grand_total = round(subtotal + tax + shipping_cost, 2)

    return CartTotals(
        quantity=quantity,
        items_subtotal=round(subtotal, 2),
        tax=tax,
        shipping_cost=round(shipping_cost, 2),
        grand_total=grand_total,
        shipping_quote=quote,
        currency=getattr(settings, "STORE_CURRENCY", "EUR"),
    )
