"""Phase 62: premium customer portal — dashboard, advanced filters, ownership, i18n.

Verifies the richer dashboard (KPIs/quick-actions/alerts/activity), the new order &
billing filters (date/total/receipt/chips, querystring-persistent), wishlist sort,
address search, security ownership, no N+1, and EN/IT/FR strings. No real PII.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, Address
from orders.models import Order, Payment


def _user(email, username):
    u = Account.objects.create_user(first_name="QA", last_name="T", username=username,
                                    email=email, password="x-test-pass")
    u.is_active = True
    u.save()
    return u


def _order(user, num, total, *, status="New", paid=False, days_ago=0):
    pay = None
    if paid:
        pay = Payment.objects.create(user=user, payment_id=f"pi_{num}",
                                     payment_method="Stripe", amount_paid=str(total), status="completed")
    o = Order.objects.create(user=user, order_number=num, order_total=total, tax=0.0,
                             status=status, is_ordered=True, payment=pay,
                             first_name="QA", last_name="T", phone="0", email=user.email,
                             address_line_1="x", country="IT", state="x", city="Rome")
    if days_ago:
        Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return o


class Phase62PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = _user("alice_p62@example.com", "alice_p62")
        cls.bob = _user("bob_p62@example.com", "bob_p62")
        cls.o1 = _order(cls.alice, "A001", 50.0, status="Completed", paid=True, days_ago=1)
        cls.o2 = _order(cls.alice, "A002", 200.0, status="New", paid=False, days_ago=40)
        cls.b1 = _order(cls.bob, "B001", 99.0, status="New", paid=True)
        Address.objects.create(user=cls.alice, first_name="A", last_name="L", email="a@x.z",
                               phone="0", address_line_1="Via Roma", city="Rome", state="RM",
                               postal_code="00100", country="IT", is_default=True)

    def setUp(self):
        # Reset the thread-local active language so reverse() yields unprefixed URLs
        # and pages render in the default language (prevents cross-test leakage).
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)
        self.client.force_login(self.alice)

    # -- dashboard ------------------------------------------------------------
    def test_dashboard_premium_render(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("dash-quick", html)         # quick actions
        self.assertIn("dash-kpi-6", html)          # expanded KPIs
        self.assertIn("Receipts", html)
        self.assertIn("Saved items", html)
        self.assertIn("dash-timeline", html)       # activity (alice has orders)

    def test_dashboard_kpis_real(self):
        ctx = self.client.get(reverse("dashboard")).context
        self.assertEqual(ctx["total_orders"], 2)
        self.assertEqual(ctx["receipts_available"], 1)   # only o1 is paid
        self.assertEqual(ctx["addresses_count"], 1)

    def test_dashboard_no_n_plus_1(self):
        # payment is select_related'd onto the recent orders, so reading
        # o.payment.payment_method for every row costs zero extra queries.
        resp = self.client.get(reverse("dashboard"))
        orders = resp.context["orders"]
        with self.assertNumQueries(0):
            for o in orders:
                _ = o.payment.payment_method if o.payment_id else None

    # -- orders filters -------------------------------------------------------
    def test_orders_total_range_filter(self):
        r = self.client.get(reverse("my_orders") + "?total_min=100")
        nums = [o.order_number for o in r.context["orders"]]
        self.assertIn("A002", nums)
        self.assertNotIn("A001", nums)

    def test_orders_receipt_filter(self):
        r = self.client.get(reverse("my_orders") + "?receipt=1")
        nums = [o.order_number for o in r.context["orders"]]
        self.assertEqual(nums, ["A001"])             # only the paid order

    def test_orders_date_range_filter(self):
        # date_from yesterday excludes the 40-days-ago order
        cutoff = (timezone.now() - timedelta(days=7)).date().isoformat()
        r = self.client.get(reverse("my_orders") + f"?date_from={cutoff}")
        nums = [o.order_number for o in r.context["orders"]]
        self.assertIn("A001", nums)
        self.assertNotIn("A002", nums)

    def test_orders_chips_and_count(self):
        html = self.client.get(reverse("my_orders")).content.decode()
        self.assertIn("portal-chip", html)
        self.assertIn("portal-result-count", html)
        self.assertIn("pf-advanced", html)

    def test_orders_querystring_preserved_in_pagination(self):
        ctx = self.client.get(reverse("my_orders") + "?status=Completed&receipt=1").context
        self.assertIn("receipt=1", ctx["querystring"])
        self.assertIn("status=Completed", ctx["querystring"])

    def test_invalid_filter_inputs_are_safe(self):
        # garbage / negative / non-finite total must not 500 and must be ignored
        for bad in ["?date_from=notadate&total_min=abc", "?total_min=-5", "?total_max=nan",
                    "?total_min=inf"]:
            r = self.client.get(reverse("my_orders") + bad)
            self.assertEqual(r.status_code, 200, bad)
            self.assertEqual(len(r.context["orders"]), 2, bad)   # filter ignored -> all orders

    # -- billing --------------------------------------------------------------
    def test_billing_summary(self):
        ctx = self.client.get(reverse("billing")).context
        self.assertEqual(ctx["summary"]["paid_count"], 1)
        self.assertEqual(ctx["summary"]["pending_count"], 1)

    # -- wishlist / address ---------------------------------------------------
    def test_wishlist_sort_safe(self):
        r = self.client.get(reverse("wishlist:saved") + "?sort=price_low")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["sort"], "price_low")

    def test_address_search(self):
        r = self.client.get(reverse("address_list") + "?q=rome")
        self.assertEqual(r.context["result_count"], 1)
        r2 = self.client.get(reverse("address_list") + "?q=zzznotfound")
        self.assertEqual(r2.context["result_count"], 0)

    # -- security / ownership -------------------------------------------------
    def test_orders_scoped_to_user(self):
        nums = [o.order_number for o in self.client.get(reverse("my_orders")).context["orders"]]
        self.assertNotIn("B001", nums)               # bob's order never shown to alice

    def test_order_detail_ownership(self):
        r = self.client.get(reverse("order_detail", args=["B001"]))
        self.assertEqual(r.status_code, 404)         # cannot view another user's order

    def test_portal_requires_login(self):
        self.client.logout()
        for name in ["dashboard", "my_orders", "billing", "address_list"]:
            r = self.client.get(reverse(name))
            self.assertIn(r.status_code, (302, 301))
            self.assertIn("login", r.headers.get("Location", "").lower())

    # -- i18n + regressions ---------------------------------------------------
    def test_dashboard_localized(self):
        base = reverse("dashboard")  # en active (setUp) -> unprefixed
        it = self.client.get("/it" + base).content.decode()
        self.assertIn("Vedi ordini", it)
        fr = self.client.get("/fr" + base).content.decode()
        self.assertIn("Voir les commandes", fr)

    def test_checkout_redirect_regression(self):
        self.client.logout()
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")
