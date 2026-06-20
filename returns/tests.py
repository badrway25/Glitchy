from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import Order
from returns.models import ReturnRequest
from returns.services import (
    default_refund_amount,
    eligibility_for_order,
    is_within_window,
)


def make_order(days_ago=0, **kw):
    kw.setdefault("is_ordered", True)
    order = Order.objects.create(
        order_number=f"TST{days_ago}",
        first_name="Mario", last_name="Rossi", phone="123", email="m@example.com",
        address_line_1="Via Roma 1", country="IT", state="RM", city="Rome",
        items_subtotal=40.0, shipping_cost=4.90, tax=0.80, order_total=45.70,
        cost_production=18.0, cost_shipping=5.50, payment_fee=1.0,
        **kw,
    )
    if days_ago:
        placed = timezone.now() - timedelta(days=days_ago)
        Order.objects.filter(pk=order.pk).update(created_at=placed)
        order.refresh_from_db()
    return order


@override_settings(RETURN_WINDOW_DAYS=14)
class ReturnEligibilityTests(TestCase):
    def test_within_window(self):
        order = make_order(days_ago=2)
        elig = eligibility_for_order(order)
        self.assertTrue(elig.eligible)
        self.assertGreaterEqual(elig.days_left, 11)

    def test_exactly_on_last_day(self):
        order = make_order(days_ago=14)
        self.assertTrue(is_within_window(order))

    def test_outside_window(self):
        order = make_order(days_ago=20)
        elig = eligibility_for_order(order)
        self.assertFalse(elig.eligible)
        self.assertEqual(elig.reason, "window_passed")

    def test_not_confirmed_order(self):
        order = make_order(days_ago=1, is_ordered=False)
        self.assertFalse(is_within_window(order))

    def test_default_refund_uses_subtotal(self):
        order = make_order(days_ago=1)
        self.assertEqual(default_refund_amount(order), 40.0)


@override_settings(RETURN_WINDOW_DAYS=14)
class ReturnMarginTests(TestCase):
    def test_margin_after_refund(self):
        order = make_order(days_ago=1)
        rr = ReturnRequest.objects.create(order=order, refund_amount=40.0, within_window=True)
        m = rr.margin_after_refund()
        # net before refund = 45.70 - 0.80 - 18 - 5.5 - 1.0 = 20.40 ; after refund 40 -> -19.60
        self.assertAlmostEqual(m.net_margin, 20.40, places=2)
        self.assertAlmostEqual(m.net_margin_after_refund, -19.60, places=2)
        # band reflects the order's pre-refund profitability (45% -> good)
        self.assertEqual(m.band, "good")
