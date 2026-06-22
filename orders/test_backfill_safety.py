"""P1: backfill cost command is dry-run by default and never fabricates costs."""
from django.test import TestCase
from orders.models import Order
from orders.services import backfill_order_costs


class BackfillSafetyTests(TestCase):
    def setUp(self):
        # an order with no OrderProducts -> no cost data available
        self.o = Order.objects.create(first_name="A", last_name="B", phone="1", email="c@x.com",
                                      address_line_1="x", city="c", state="s", country="IT",
                                      order_total=20, tax=0, ip="1", order_number="BF1",
                                      is_ordered=True, cost_production=0)

    def test_dry_run_writes_nothing(self):
        before = self.o.cost_production
        s = backfill_order_costs(only_zero=True, dry_run=True)
        self.o.refresh_from_db()
        self.assertEqual(self.o.cost_production, before)   # unchanged
        self.assertIn("examined", s)

    def test_no_cost_data_is_not_fabricated(self):
        # apply, but with no Printify/base cost data the order stays at 0 (honest)
        backfill_order_costs(only_zero=True, dry_run=False)
        self.o.refresh_from_db()
        self.assertEqual(self.o.cost_production, 0)

    def test_idempotent(self):
        backfill_order_costs(only_zero=True, dry_run=False)
        c1 = Order.objects.get(order_number="BF1").cost_production
        backfill_order_costs(only_zero=True, dry_run=False)
        c2 = Order.objects.get(order_number="BF1").cost_production
        self.assertEqual(c1, c2)
