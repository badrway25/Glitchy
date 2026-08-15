"""Checkout money — ONE engine for the summary, the widget, the order and payments.

Before this module two independent engines priced shipping:

* `shipping.services.quote_for_cart` (settings rate table) drove the server-rendered
  Order summary **and** the real order/payment amounts, using the IP/session country;
* `printify_integration.shipping_estimator.estimate_for_cart` (Printify profiles/live)
  drove the "Estimate delivery" widget, using the country typed in the form.

They disagreed on the same cart and the same country (IT: 4.90 vs 10.00), the widget's
result was never persisted, and the customer's chosen method was discarded. This module
replaces both entry points with a single `checkout_quote()` that returns the whole money
picture plus the delivery options, so every surface repaints from one payload and the
customer is charged exactly what they were shown.

Shipping cost resolution (in order): live Printify cost map for the destination →
catalog/profile or local rate table via the estimator → unavailable. Express is layered
on top and is only ever offered when Printify priced it AND `shipping.express` finds no
blockers (US mainland, no PO Box, eligible items, phone present).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .express import (EXPRESS_METHOD, express_blockers,
                      express_eligible_item_count, is_express)

STANDARD = "standard"


def _currency() -> str:
    return getattr(settings, "STORE_CURRENCY", "EUR")


def _symbol() -> str:
    return getattr(settings, "STORE_CURRENCY_SYMBOL", "€")


def money(value) -> str:
    return f"{_symbol()} {float(value or 0):,.2f}"


@dataclass
class CheckoutQuote:
    """Everything a checkout surface needs, computed once."""

    available: bool
    country: str
    currency: str
    method: str = STANDARD
    items_subtotal: float = 0.0
    discount: float = 0.0
    shipping_cost: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0
    free: bool = False
    quantity: int = 0
    source: str = ""
    message: str = ""
    delivery_label: str = ""
    delivery_days_min: int = 0
    delivery_days_max: int = 0
    estimated_delivery_from: str = ""
    estimated_delivery_to: str = ""
    options: list = field(default_factory=list)          # list[dict], JSON-safe
    express_blockers: list = field(default_factory=list)  # safe codes
    express_eligible_items: int = 0
    errors_safe: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "country": self.country,
            "currency": self.currency,
            "method": self.method,
            "items_subtotal": self.items_subtotal,
            "items_subtotal_display": money(self.items_subtotal),
            "discount": self.discount,
            "discount_display": money(self.discount),
            "shipping_cost": self.shipping_cost,
            "shipping_display": _("Free") if self.free or not self.shipping_cost
                                else money(self.shipping_cost),
            "tax": self.tax,
            "tax_display": money(self.tax),
            "grand_total": self.grand_total,
            "grand_total_display": money(self.grand_total),
            "free": self.free,
            "quantity": self.quantity,
            "source": self.source,
            "message": str(self.message or ""),
            "delivery_label": str(self.delivery_label or ""),
            "delivery_days_min": self.delivery_days_min,
            "delivery_days_max": self.delivery_days_max,
            "estimated_delivery_from": self.estimated_delivery_from,
            "estimated_delivery_to": self.estimated_delivery_to,
            "options": self.options,
            "express_blockers": self.express_blockers,
            "express_eligible_items": self.express_eligible_items,
            "errors_safe": self.errors_safe,
        }


def _subtotal_and_qty(cart_items):
    subtotal = 0.0
    quantity = 0
    for item in cart_items or []:
        qty = int(getattr(item, "quantity", 0) or 0)
        price = float(getattr(getattr(item, "product", None), "price", 0) or 0)
        quantity += qty
        subtotal += price * qty
    return round(subtotal, 2), quantity


def tax_for(subtotal: float) -> float:
    rate = float(getattr(settings, "STORE_TAX_RATE", 0) or 0)
    return round(float(subtotal) * rate / 100.0, 2)


def checkout_quote(cart_items, *, country, postal_code="", state="", city="",
                   address1="", address2="", phone="", email=None,
                   method="", discount=0.0, _cost_map_cents=None):
    """Price the cart for one destination and one shipping method.

    `_cost_map_cents` is a test/seam hook: when given, it stands in for the live
    Printify `POST /orders/shipping.json` response ({"standard": 499, ...} in cents).
    """
    from printify_integration.shipping_estimator import SOURCE_LIVE, estimate_for_cart

    cart_items = list(cart_items or [])
    country = (country or getattr(settings, "SHIPPING_DEFAULT_COUNTRY", "IT")).upper()
    currency = _currency()
    subtotal, quantity = _subtotal_and_qty(cart_items)
    discount = round(float(discount or 0), 2)

    blockers = express_blockers(cart_items, country=country, state=state,
                                address1=address1, address2=address2,
                                phone=phone, email=email)
    eligible_items = express_eligible_item_count(cart_items)

    if not cart_items:
        return CheckoutQuote(available=False, country=country, currency=currency,
                             message=_("Add an item to estimate delivery."),
                             express_blockers=blockers, errors_safe=["empty_cart"])

    estimate = estimate_for_cart(
        cart_items, country, postal_code=postal_code, city=city, region=state,
        shipping_method=method or STANDARD, subtotal=subtotal, use_cache=False,
        cost_map_cents=_cost_map_cents)

    if not estimate.available:
        return CheckoutQuote(
            available=False, country=country, currency=currency,
            items_subtotal=subtotal, quantity=quantity, discount=discount,
            message=estimate.disclaimer, express_blockers=blockers,
            express_eligible_items=eligible_items,
            errors_safe=list(estimate.errors_safe or []))

    # ---- options: only offer what Printify actually priced --------------------
    # Without a live cost map the estimator labels its single fallback option with
    # whatever method was asked for and prices it from the local rate table. Offering
    # "express"/"priority" there would charge the standard rate for a premium service
    # and still submit the order as Express — so anything other than standard is
    # dropped unless the price came from Printify.
    live_priced = estimate.source == SOURCE_LIVE
    options = []
    for opt in estimate.options:
        data = opt.as_dict()
        method_name = data["method"]
        # `is_express` covers BOTH keys Printify uses ("express" and
        # "printify_express") — they route to the same express endpoint, so they
        # must pass the same eligibility gate.
        if is_express(method_name) and blockers:
            continue          # never advertise what we cannot deliver
        if not live_priced and method_name != STANDARD:
            continue          # we have no real price for this method
        data["fastest"] = is_express(method_name)
        options.append(data)
    if not options:
        # Nothing survived: fall back to a standard-priced option so the shopper
        # always sees one honest price (never a premium method at the standard rate).
        base = next((o.as_dict() for o in estimate.options if o.method == STANDARD),
                    estimate.options[0].as_dict())
        base["method"] = STANDARD
        base["fastest"] = False
        options = [base]

    available_methods = [o["method"] for o in options]
    chosen = method if method in available_methods else (
        estimate.selected_method if estimate.selected_method in available_methods
        else available_methods[0])
    for data in options:
        data["selected"] = data["method"] == chosen

    chosen_option = next(o for o in options if o["method"] == chosen)
    shipping_cost = round(float(chosen_option["cost"] or 0), 2)
    free = bool(chosen_option.get("free")) or shipping_cost == 0.0
    tax = tax_for(subtotal)
    grand_total = round(max(0.0, subtotal + tax + shipping_cost - discount), 2)

    return CheckoutQuote(
        available=True, country=country, currency=currency, method=chosen,
        items_subtotal=subtotal, discount=discount, shipping_cost=shipping_cost,
        tax=tax, grand_total=grand_total, free=free, quantity=quantity,
        source=estimate.source, message=estimate.disclaimer,
        delivery_label=chosen_option.get("delivery_label", "") or estimate.delivery_label,
        delivery_days_min=chosen_option.get("delivery_days_min", 0),
        delivery_days_max=chosen_option.get("delivery_days_max", 0),
        estimated_delivery_from=estimate.estimated_delivery_from,
        estimated_delivery_to=estimate.estimated_delivery_to,
        options=options, express_blockers=blockers,
        express_eligible_items=eligible_items,
        errors_safe=list(estimate.errors_safe or []))
