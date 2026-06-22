"""P1: refund idempotency, search redirects to filter pipeline."""
from django.test import Client, TestCase
from django.urls import reverse


class SearchRedirectTests(TestCase):
    def test_search_redirects_to_store_with_query(self):
        c = Client()
        r = c.get(reverse("search"), {"keyword": "tee", "sale": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/store/", r.url)
        self.assertIn("keyword=tee", r.url)
        self.assertIn("sale=1", r.url)

    def test_search_no_results_has_discovery_after_redirect(self):
        # following the redirect lands on the store page with recommendations on no-results
        c = Client()
        r = c.get(reverse("search"), {"keyword": "zzzznotfound"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("recommendations", r.context)
        self.assertTrue(r.context["has_filters"])


class RefundIdempotencyTests(TestCase):
    def setUp(self):
        from accounts.models import Account
        from orders.models import Order
        from returns.models import ReturnRequest
        self.Order, self.RR = Order, ReturnRequest
        self.u = Account.objects.create_user(email="r@x.com", first_name="R", last_name="R",
                                              username="r", password="pw12345!")
        self.order = Order.objects.create(user=self.u, first_name="R", last_name="R", phone="1",
                                          email="r@x.com", address_line_1="x", city="c", state="s",
                                          country="IT", order_total=100, tax=0, ip="1",
                                          order_number="REF1", is_ordered=True, refunded_amount=0)

    def _refund_request(self, amount):
        return self.RR.objects.create(order=self.order, customer_email="r@x.com",
                                      refund_amount=amount, status="approved")

    def test_mark_refunded_is_idempotent(self):
        from returns.admin import ReturnRequestAdmin
        from returns.models import ReturnRequest
        from django.contrib.admin.sites import AdminSite
        rr = self._refund_request(30)
        admin = ReturnRequestAdmin(ReturnRequest, AdminSite())

        class Req:  # minimal request stub for message_user
            def __init__(self): self._messages = []
        from django.test import RequestFactory
        req = RequestFactory().post("/")
        # attach messages framework
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", {}); setattr(req, "_messages", FallbackStorage(req))
        qs = ReturnRequest.objects.filter(pk=rr.pk)
        admin.mark_refunded(req, qs)
        self.order.refresh_from_db()
        self.assertEqual(self.order.refunded_amount, 30.0)
        # run AGAIN on the same refunded request -> still 30 (no double count)
        admin.mark_refunded(req, ReturnRequest.objects.filter(pk=rr.pk))
        self.order.refresh_from_db()
        self.assertEqual(self.order.refunded_amount, 30.0)
