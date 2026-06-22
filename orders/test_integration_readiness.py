"""Phase 28: production-readiness mock tests — Stripe webhook + Printify push.
No real keys, no real network, no real orders. Proves the server-authoritative paths."""
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from orders.models import Order, Payment


def _order(num="WH1", paid=False, **kw):
    d = dict(first_name="A", last_name="B", phone="1", email="c@x.com", address_line_1="x",
             city="c", state="s", country="IT", order_total=120, tax=0, ip="1",
             order_number=num, is_ordered=paid, currency="EUR")
    d.update(kw)
    return Order.objects.create(**d)


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.url = reverse("stripe_webhook")

    def _event(self, etype, obj):
        return {"type": etype, "data": {"object": obj}}

    def test_invalid_signature_rejected(self):
        with patch("stripe.Webhook.construct_event", side_effect=ValueError("bad sig")):
            r = self.c.post(self.url, data=b"{}", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="t=1,v1=bad")
        self.assertEqual(r.status_code, 400)

    def test_payment_intent_succeeded_finalizes(self):
        o = _order("WH-OK")
        ev = self._event("payment_intent.succeeded",
                         {"id": "pi_1", "amount": 12000, "status": "succeeded",
                          "metadata": {"order_number": "WH-OK"}})
        with patch("stripe.Webhook.construct_event", return_value=ev), \
             patch("orders.services.finalize_from_intent") as fin:
            r = self.c.post(self.url, data=b"{}", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="ok")
        self.assertEqual(r.status_code, 200)
        fin.assert_called_once()
        self.assertEqual(fin.call_args.kwargs["order_number"], "WH-OK")

    def test_charge_refunded_applies_refund(self):
        ev = self._event("charge.refunded",
                         {"payment_intent": "pi_9", "amount_refunded": 5000})
        with patch("stripe.Webhook.construct_event", return_value=ev), \
             patch("orders.services.apply_stripe_refund") as ref:
            r = self.c.post(self.url, data=b"{}", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="ok")
        self.assertEqual(r.status_code, 200)
        ref.assert_called_once()
        self.assertEqual(ref.call_args.kwargs["amount_refunded_cents"], 5000)

    def test_payment_failed_does_not_finalize(self):
        o = _order("WH-FAIL")
        ev = self._event("payment_intent.payment_failed",
                         {"id": "pi_2", "metadata": {"order_number": "WH-FAIL"}})
        with patch("stripe.Webhook.construct_event", return_value=ev):
            r = self.c.post(self.url, data=b"{}", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="ok")
        self.assertEqual(r.status_code, 200)
        o.refresh_from_db()
        self.assertFalse(o.is_ordered)


class PrintifyPushGatingTests(TestCase):
    @override_settings(PRINTIFY_PUSH_ENABLED=False)
    def test_push_disabled_does_not_create_real_order(self):
        from orders.services import push_order_to_printify
        o = _order("PUSH-OFF", paid=True)
        with patch("orders.services.create_order") as create:
            res = push_order_to_printify(o, auto_send=False)
        self.assertIsNone(res)
        create.assert_not_called()             # no real Printify order
        o.refresh_from_db()
        self.assertEqual(o.printify_status, "push_disabled")

    @override_settings(PRINTIFY_PUSH_ENABLED=True)
    def test_already_pushed_is_idempotent(self):
        from orders.services import push_order_to_printify
        o = _order("PUSH-DUP", paid=True, printify_order_id="po_existing")
        with patch("orders.services.create_order") as create:
            res = push_order_to_printify(o, auto_send=False)
        self.assertEqual(res, "po_existing")   # returns existing, no new order
        create.assert_not_called()
