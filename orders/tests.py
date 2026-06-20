from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

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


@override_settings(
    N8N_ENABLED=False, EMAIL_SMTP_FALLBACK=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="shop@example.com", SHIPPING_USE_PRINTIFY=False,
)
class StripeWebhookTests(TestCase):
    def setUp(self):
        from category.models import Category
        from store.models import Product
        from carts.models import Cart, CartItem
        from orders.models import Order

        cat = Category.objects.create(category_name="Tees", slug="tees-wh")
        self.product = Product.objects.create(
            product_name="WH Tee", slug="wh-tee", description="d", price=25, stock=5,
            is_available=True, category=cat, printify_product_id="ppwh", base_cost=10.0)
        self.cart = Cart.objects.create(cart_id="sesskey1")
        CartItem.objects.create(product=self.product, cart=self.cart, quantity=2, is_active=True)
        self.order = Order.objects.create(
            order_number="WH123", first_name="G", last_name="U", phone="1",
            email="g@example.com", address_line_1="x", country="IT", state="s", city="c",
            items_subtotal=50.0, shipping_cost=0.0, tax=1.0, order_total=51.0,
            is_guest=True, session_key="sesskey1", is_ordered=False)

    def _post(self, event):
        with patch("orders.views.stripe.Webhook.construct_event", return_value=event):
            return self.client.post(reverse("stripe_webhook"), data=b"{}",
                                    content_type="application/json",
                                    HTTP_STRIPE_SIGNATURE="t=1,v1=sig")

    SUCCEEDED = {"type": "payment_intent.succeeded", "data": {"object": {
        "id": "pi_1", "status": "succeeded", "amount": 5100,
        "metadata": {"order_number": "WH123"}}}}

    def test_invalid_signature_returns_400(self):
        with patch("orders.views.stripe.Webhook.construct_event", side_effect=ValueError("bad sig")):
            resp = self.client.post(reverse("stripe_webhook"), data=b"{}",
                                    content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_payment_succeeded_finalizes_order(self):
        from orders.models import OrderProduct, Payment

        resp = self._post(self.SUCCEEDED)
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_ordered)
        self.assertEqual(OrderProduct.objects.filter(order=self.order).count(), 1)
        self.assertTrue(Payment.objects.filter(payment_id="pi_1").exists())
        # production cost snapshotted (2 × base_cost 10)
        self.assertAlmostEqual(self.order.cost_production, 20.0, places=2)

    def test_webhook_is_idempotent(self):
        from orders.models import OrderProduct

        self._post(self.SUCCEEDED)
        self._post(self.SUCCEEDED)  # duplicate delivery
        self.assertEqual(OrderProduct.objects.filter(order=self.order).count(), 1)

    def test_charge_refunded_records_amount(self):
        self._post(self.SUCCEEDED)
        refund = {"type": "charge.refunded", "data": {"object": {
            "payment_intent": "pi_1", "amount_refunded": 2500}}}
        self._post(refund)
        self.order.refresh_from_db()
        self.assertEqual(self.order.refunded_amount, 25.0)
        # idempotent: same cumulative refund again doesn't change it
        self._post(refund)
        self.order.refresh_from_db()
        self.assertEqual(self.order.refunded_amount, 25.0)

    def test_payment_failed_does_not_finalize(self):
        event = {"type": "payment_intent.payment_failed", "data": {"object": {
            "metadata": {"order_number": "WH123"}}}}
        resp = self._post(event)
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_ordered)
