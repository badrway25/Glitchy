"""Supplier cost & margin simulator (admin/ops tool).

Pure calculation — never creates an order, never calls payment, never pushes to Printify.
Combines customer price, real/fallback shipping, supplier production cost and the estimated
payment fee into a gross/net margin. Safe for admin display; never shown to customers.
"""
from dataclasses import dataclass, asdict

from django.conf import settings


@dataclass
class MarginSimulation:
    currency: str
    quantity: int
    country: str
    customer_subtotal: float
    discount: float
    shipping_paid: float
    shipping_source: str
    tax: float
    supplier_production_cost: float
    supplier_shipping_cost: float
    payment_fee: float
    gross_margin: float
    net_margin: float
    margin_pct: float
    low_margin_warning: bool

    def as_dict(self):
        return asdict(self)


def _payment_fee(amount):
    pct = float(getattr(settings, "PAYMENT_FEE_PERCENT", 0) or 0) / 100.0
    fixed = float(getattr(settings, "PAYMENT_FEE_FIXED", 0) or 0)
    return round(amount * pct + fixed, 2)


def simulate_margin(*, product, variant=None, quantity=1, country="IT",
                    coupon_pct=0.0, shipping_source="auto"):
    """Return a MarginSimulation. shipping_source: 'auto' | 'printify' | 'fallback'."""
    currency = getattr(settings, "STORE_CURRENCY", "EUR")
    qty = max(1, int(quantity or 1))
    unit_price = float(getattr(variant or product, "price", None) or product.price)
    subtotal = round(unit_price * qty, 2)
    discount = round(subtotal * (float(coupon_pct or 0) / 100.0), 2)
    net_revenue = subtotal - discount

    # Supplier production cost: variant cost overrides product base_cost.
    unit_cost = 0.0
    if variant is not None and getattr(variant, "production_cost", 0):
        unit_cost = float(variant.production_cost)
    elif getattr(product, "base_cost", 0):
        unit_cost = float(product.base_cost)
    supplier_production = round(unit_cost * qty, 2)

    # Shipping (customer-paid) + supplier shipping cost when Printify is the source.
    from shipping.services import quote_for_cart, fallback_quote

    class _CI:
        def __init__(self, p, q): self.product = p; self.quantity = q
    cart = [_CI(product, qty)]

    if shipping_source == "fallback":
        q = fallback_quote(country, qty, subtotal)
    else:
        # 'auto' respects SHIPPING_USE_PRINTIFY; 'printify' forces the hook attempt.
        if shipping_source == "printify":
            from django.test import override_settings
            with override_settings(SHIPPING_USE_PRINTIFY=True):
                q = quote_for_cart(country, cart, subtotal=subtotal)
        else:
            q = quote_for_cart(country, cart, subtotal=subtotal)
    shipping_paid = float(q.cost) if q.available else 0.0
    # supplier shipping cost ≈ what we pay Printify (same profile when source=printify)
    supplier_shipping = shipping_paid if q.source == "printify" else 0.0

    tax_rate = float(getattr(settings, "STORE_TAX_RATE", 0) or 0) / 100.0
    tax = round(net_revenue * tax_rate, 2)

    customer_total = net_revenue + shipping_paid + tax
    payment_fee = _payment_fee(customer_total)

    gross_margin = round(net_revenue - supplier_production, 2)
    net_margin = round(net_revenue + shipping_paid - supplier_production
                       - supplier_shipping - payment_fee, 2)
    margin_pct = round(100 * net_margin / net_revenue, 1) if net_revenue else 0.0
    # Warn on the PRODUCT (gross) margin — independent of customer-paid shipping.
    gross_pct = (100 * gross_margin / net_revenue) if net_revenue else 0.0

    return MarginSimulation(
        currency=currency, quantity=qty, country=country.upper(),
        customer_subtotal=subtotal, discount=discount, shipping_paid=round(shipping_paid, 2),
        shipping_source=q.source, tax=tax, supplier_production_cost=supplier_production,
        supplier_shipping_cost=round(supplier_shipping, 2), payment_fee=payment_fee,
        gross_margin=gross_margin, net_margin=net_margin, margin_pct=margin_pct,
        low_margin_warning=gross_pct < 15.0)
