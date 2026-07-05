"""PayPal Orders v2 payload builder — deterministic, Decimal-only, checkout-snapshot based.

Root cause this replaces: the JS created the PayPal order CLIENT-SIDE with a bare
``{amount: {value: grand_total}}`` — no items, no breakdown, no shipping, no phone — so the
popup showed the buyer's wallet address and context-free totals. The payload is now built
server-side from the pending Order (the checkout snapshot: address, phone already E.164,
totals with shipping/tax/coupon) plus the live cart items.

Invariants:
- Decimal everywhere, 2-dp strings in the payload (never float maths);
- the breakdown ALWAYS balances: discount is derived as
  item_total + shipping + tax − order_total (clamped ≥ 0), so amount.value is the REAL
  Glitchy grand total by construction;
- an explicit consistency check refuses to build if the identity still doesn't hold;
- ``SET_PROVIDED_ADDRESS`` so PayPal shows the checkout address, not the wallet default;
- the phone is included only when it parses as a valid E.164 number;
- no PII is ever logged (callers log only safe codes/amounts).
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

TWO = Decimal("0.01")


def _d(value):
    return Decimal(str(value or 0)).quantize(TWO, rounding=ROUND_HALF_UP)


def _m(value, currency):
    return {"currency_code": currency, "value": f"{_d(value):.2f}"}


class PayloadMismatch(Exception):
    """The computed breakdown does not reproduce the order total — refuse to create."""


def _phone_fields(e164):
    """('39', '3331234567') from '+393331234567' — only for valid parseable numbers."""
    try:
        import phonenumbers
        parsed = phonenumbers.parse(e164 or "", None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return str(parsed.country_code), str(parsed.national_number)
    except Exception:
        return None


def build_order_payload(order, cart_items, *, currency=None, brand_name=None, locale=None):
    """Full Orders v2 payload from the pending Order + live cart items."""
    currency = (currency or getattr(settings, "PAYPAL_CURRENCY", "EUR")).upper()
    brand_name = brand_name or getattr(settings, "SITE_NAME", "Glitchy")

    items, item_total = [], Decimal("0.00")
    for ci in cart_items:
        unit = _d(ci.product.price)
        qty = int(ci.quantity)
        item_total += unit * qty
        items.append({
            "name": (ci.product.product_name or "Item")[:127],
            "unit_amount": _m(unit, currency),
            "quantity": str(qty),
            "category": "PHYSICAL_GOODS",
        })

    shipping_total = _d(getattr(order, "shipping_cost", 0))
    tax_total = _d(getattr(order, "tax", 0))
    grand = _d(order.order_total)
    # derived discount keeps the identity exact even when a coupon was applied
    discount = item_total + shipping_total + tax_total - grand
    if discount < 0:
        raise PayloadMismatch(
            f"components below order total (items={item_total} ship={shipping_total} "
            f"tax={tax_total} total={grand})")
    discount = _d(discount)

    # hard consistency check — the whole point of this module
    if item_total + shipping_total + tax_total - discount != grand:
        raise PayloadMismatch("breakdown does not reproduce the order total")
    if grand <= 0:
        raise PayloadMismatch("non-positive order total")

    shipping = {
        "name": {"full_name": f"{order.first_name} {order.last_name}".strip()[:300]},
        "address": {
            "address_line_1": (order.address_line_1 or "")[:300],
            "address_line_2": (getattr(order, "address_line_2", "") or "")[:300],
            "admin_area_2": (order.city or "")[:120],          # city
            "admin_area_1": (order.state or "")[:300],          # province/state
            "postal_code": (order.postal_code or "")[:60],
            "country_code": (order.country or "").upper()[:2],
        },
    }
    phone = _phone_fields(getattr(order, "phone", ""))
    if phone:
        shipping["phone_number"] = {"country_code": phone[0], "national_number": phone[1]}

    return {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": order.order_number,
            "invoice_id": order.order_number,
            "description": f"{brand_name} order {order.order_number}"[:127],
            "amount": {
                **_m(grand, currency),
                "breakdown": {
                    "item_total": _m(item_total, currency),
                    "shipping": _m(shipping_total, currency),
                    "tax_total": _m(tax_total, currency),
                    "discount": _m(discount, currency),
                },
            },
            "items": items,
            "shipping": shipping,
        }],
        # application_context (NOT payment_source.paypal.experience_context): orders created
        # with an explicit payment_source push PayPal into the payer-action redirect flow,
        # which fights the JS SDK Buttons popup (symptom: an extra blank window + a client
        # capture that hangs ~1min then errors). application_context carries the same
        # preferences and is the SDK-Buttons-compatible shape.
        "application_context": {
            "shipping_preference": "SET_PROVIDED_ADDRESS",
            "user_action": "PAY_NOW",
            "brand_name": brand_name[:127],
            **({"locale": locale} if locale else {}),
        },
    }
