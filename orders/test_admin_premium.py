"""Phase 68 admin — orders changelist premium rendering (status pills + cohesive KPI cards)."""
from django.test import TestCase, override_settings

from accounts.models import Account
from orders.models import Order, Payment


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class OrdersAdminPremiumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        pay = Payment.objects.create(user=cls.su, payment_id="p1", payment_method="card",
                                     amount_paid="59", status="completed")
        cls.order = Order.objects.create(
            user=cls.su, order_number="X1", first_name="QA", last_name="Demo", email="q@e.com",
            status="Completed", is_ordered=True, order_total=59, tax=0, cost_production=10,
            cost_shipping=3, payment_fee=1, refunded_amount=0, items_subtotal=55,
            shipping_cost=4, payment=pay, currency="EUR")

    def test_changelist_renders_with_premium_badges(self):
        self.client.force_login(self.su)
        resp = self.client.get("/admin/orders/order/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("border-radius:999px", html)                 # status/margin pills
        self.assertNotIn("#0f172a", html)                          # no legacy dark KPI card
        # KPI cards now share one cohesive surface style
        self.assertGreaterEqual(html.count("border:1px solid rgba(120,120,120,.22)"), 5)

    def test_changelist_masks_customer_pii(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/orders/order/").content.decode()
        # the raw email is never shown in full
        self.assertNotIn("q@e.com", html)
