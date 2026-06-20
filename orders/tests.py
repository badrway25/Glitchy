from django.test import TestCase, override_settings

from orders.margins import (
    compute_margins_from_values,
    estimate_payment_fee,
)


class MarginMathTests(TestCase):
    def test_spec_example(self):
        # Customer pays 49.90, Printify 18.00, shipping 5.50, fee 1.50.
        m = compute_margins_from_values(
            order_total=49.90, tax=0.0,
            cost_production=18.0, cost_shipping=5.50, payment_fee=1.50,
        )
        self.assertAlmostEqual(m.net_margin, 24.90, places=2)
        self.assertEqual(m.band, "good")

    def test_tax_excluded_from_revenue(self):
        m = compute_margins_from_values(order_total=100, tax=20, cost_production=30)
        self.assertAlmostEqual(m.revenue_ex_tax, 80.0, places=2)
        self.assertAlmostEqual(m.net_margin, 50.0, places=2)

    def test_negative_margin_band(self):
        m = compute_margins_from_values(order_total=20, cost_production=25)
        self.assertLess(m.net_margin, 0)
        self.assertEqual(m.band, "negative")

    def test_low_margin_band(self):
        m = compute_margins_from_values(order_total=100, cost_production=85)
        self.assertEqual(m.band, "low")

    def test_refund_reduces_margin(self):
        m = compute_margins_from_values(
            order_total=100, cost_production=40, refunded_amount=30)
        self.assertAlmostEqual(m.net_margin, 60.0, places=2)
        self.assertAlmostEqual(m.net_margin_after_refund, 30.0, places=2)

    def test_zero_revenue_safe(self):
        m = compute_margins_from_values(order_total=0)
        self.assertEqual(m.margin_pct, 0.0)

    def test_payment_fee_estimate(self):
        self.assertAlmostEqual(estimate_payment_fee(100, percent=1.5, fixed=0.25), 1.75, places=2)


class _Item:
    def __init__(self, price, qty):
        self.product = type("P", (), {"price": price})()
        self.quantity = qty


@override_settings(
    STORE_TAX_RATE=2.0,
    SHIPPING_FALLBACK_RATES={"IT": {"first": 4.90, "additional": 1.90, "min_days": 3, "max_days": 6}},
    SHIPPING_FREE_THRESHOLD=80, SHIPPING_DEFAULT_COUNTRY="IT", SHIPPING_USE_PRINTIFY=False,
    SHIPPING_SUPPORTED_COUNTRIES=[],
)
class CartTotalsTests(TestCase):
    def test_totals_include_shipping_and_tax(self):
        from orders.totals import compute_cart_totals

        totals = compute_cart_totals([_Item(20, 1), _Item(10, 1)], "IT")  # subtotal 30
        self.assertEqual(totals.items_subtotal, 30.0)
        self.assertEqual(totals.shipping_cost, 6.80)   # 4.90 + 1.90
        self.assertAlmostEqual(totals.tax, 0.60, places=2)
        self.assertAlmostEqual(totals.grand_total, 37.40, places=2)

    def test_free_shipping_over_threshold(self):
        from orders.totals import compute_cart_totals

        totals = compute_cart_totals([_Item(100, 1)], "IT")
        self.assertEqual(totals.shipping_cost, 0.0)
        self.assertTrue(totals.shipping_quote.free)
