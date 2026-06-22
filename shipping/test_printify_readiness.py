"""Phase 28: Printify shipping hook readiness (mocked — no real API)."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from shipping.services import quote_for_cart, ShippingQuote


class _Item:
    quantity = 1

    class product:
        price = 30


def _quote(**kw):
    base = dict(country="IT", cost=4.2, currency="EUR", min_days=2, max_days=4,
                source="printify")
    base.update(kw)
    return ShippingQuote(**base)


class PrintifyShippingHookTests(TestCase):
    @override_settings(SHIPPING_USE_PRINTIFY=False)
    def test_fallback_used_when_disabled(self):
        q = quote_for_cart("IT", [_Item()], subtotal=30)
        self.assertIn(q.source, ("fallback", "free"))

    @override_settings(SHIPPING_USE_PRINTIFY=True)
    def test_printify_quote_used_when_available(self):
        with patch("printify_integration.shipping.printify_cart_quote", return_value=_quote()):
            q = quote_for_cart("IT", [_Item()], subtotal=30)
        self.assertEqual(q.source, "printify")
        self.assertEqual(q.cost, 4.2)

    @override_settings(SHIPPING_USE_PRINTIFY=True)
    def test_falls_back_when_printify_raises(self):
        with patch("printify_integration.shipping.printify_cart_quote",
                   side_effect=TimeoutError("api down")):
            q = quote_for_cart("IT", [_Item()], subtotal=30)
        self.assertIn(q.source, ("fallback", "free"))   # never errors

    @override_settings(SHIPPING_USE_PRINTIFY=True)
    def test_falls_back_when_printify_returns_none(self):
        with patch("printify_integration.shipping.printify_cart_quote", return_value=None):
            q = quote_for_cart("IT", [_Item()], subtotal=30)
        self.assertIn(q.source, ("fallback", "free"))
