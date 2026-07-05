"""Premium order-complete: honest timeline, status polling, email idempotency.

No real n8n/SMTP/Printify calls — everything local or mocked.
"""
import pathlib

from django.conf import settings
from django.test import Client, TestCase, override_settings

from orders.timeline import get_order_timeline, timeline_summary

BASE = pathlib.Path(settings.BASE_DIR)


def _mk_order(**kw):
    from importlib import import_module
    from category.models import Category
    from store.models import Product
    from orders.models import Order, OrderProduct, Payment
    eng = import_module(settings.SESSION_ENGINE)
    ss = eng.SessionStore(); ss.create()
    cat, _ = Category.objects.get_or_create(category_name="Tees", slug="tees")
    p, _ = Product.objects.get_or_create(
        product_name="Tee", slug="tee-oc", category=cat,
        defaults={"price": 19.0, "stock": 5, "is_available": True, "description": "t"})
    pay = Payment.objects.create(payment_id=kw.pop("payment_id", "CAP-T1"),
                                 email="t@example.com", payment_method="PayPal",
                                 amount_paid="45.42", status="COMPLETED")
    base = dict(order_number="T-OC-1", first_name="M", last_name="R", email="t@example.com",
                phone="+393331234567", address_line_1="Via Roma 1", country="IT", state="MI",
                city="Milano", postal_code="20100", order_total=45.42, tax=0.9,
                shipping_cost=6.9, ip="127.0.0.1", is_ordered=True, status="Accepted",
                payment=pay, is_guest=True, session_key=ss.session_key)
    base.update(kw)
    o = Order.objects.create(**base)
    OrderProduct.objects.create(order_id=o.id, payment=pay, product_id=p.id,
                                quantity=2, product_price=19.0, ordered=True)
    return o, ss.session_key


class TimelineTests(TestCase):
    def _statuses(self, order):
        return {s["key"]: s["status"] for s in get_order_timeline(order)}

    def test_payment_only_is_sync_pending(self):
        o, _ = _mk_order()
        st = self._statuses(o)
        self.assertEqual(st["payment"], "done")
        self.assertEqual(st["printify"], "current")          # sync pending, honest
        self.assertEqual(st["production"], "pending")
        self.assertEqual(st["shipped"], "pending")           # NEVER shipped without data
        self.assertEqual(timeline_summary(o), "sync_pending")

    def test_sent_to_printify(self):
        o, _ = _mk_order(printify_order_id="PRF-1")
        st = self._statuses(o)
        self.assertEqual(st["printify"], "done")
        self.assertEqual(st["production"], "current")
        self.assertEqual(timeline_summary(o), "sent_to_printify")

    def test_in_production(self):
        o, _ = _mk_order(printify_order_id="PRF-1", printify_status="in-production")
        st = self._statuses(o)
        self.assertEqual(st["production"], "done")
        self.assertEqual(st["shipped"], "current")
        self.assertEqual(timeline_summary(o), "in_production")

    def test_shipped_requires_tracking_or_status(self):
        o, _ = _mk_order(printify_order_id="PRF-1", printify_status="in-production",
                         tracking_number="TRK1", tracking_url="https://t.example/1")
        st = self._statuses(o)
        self.assertEqual(st["shipped"], "done")
        self.assertEqual(st["delivered"], "current")
        self.assertEqual(timeline_summary(o), "shipped")
        step = [s for s in get_order_timeline(o) if s["key"] == "shipped"][0]
        self.assertEqual(step["action_url"], "https://t.example/1")

    def test_error_state_when_push_failed(self):
        o, _ = _mk_order(printify_last_error="mapping missing")
        st = self._statuses(o)
        self.assertEqual(st["printify"], "error")
        self.assertEqual(timeline_summary(o), "sync_error")

    def test_delivered(self):
        o, _ = _mk_order(printify_order_id="P", printify_status="delivered")
        self.assertEqual(self._statuses(o)["delivered"], "done")
        self.assertEqual(timeline_summary(o), "delivered")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class OrderStatusEndpointTests(TestCase):
    def test_owner_scoped_and_json_shape(self):
        o, sk = _mk_order()
        c = Client()
        # anonymous with the RIGHT session key
        session = c.session; session.create() if not c.session.session_key else None
        # simulate the owning guest session
        from importlib import import_module
        eng = import_module(settings.SESSION_ENGINE)
        c.cookies[settings.SESSION_COOKIE_NAME] = sk
        r = c.get(f"/orders/status/?order_number={o.order_number}")
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["production_status"], "sync_pending")
        self.assertEqual(len(d["timeline"]), 5)
        self.assertNotIn("Via Roma", str(d))                 # no PII in the JSON
        self.assertNotIn("t@example.com", str(d))

    def test_foreign_session_denied(self):
        o, _ = _mk_order()
        c = Client(); c.get("/")
        r = c.get(f"/orders/status/?order_number={o.order_number}")
        self.assertEqual(r.status_code, 404)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class OrderCompletePageTests(TestCase):
    def test_new_logo_no_old_logo_no_fake_steps(self):
        o, sk = _mk_order()
        c = Client()
        c.cookies[settings.SESSION_COOKIE_NAME] = sk
        html = c.get(f"/orders/order_complete/?order_number={o.order_number}"
                     f"&payment_id={o.payment.payment_id}").content.decode()
        self.assertIn("brand/logo-glitchy-nav", html)        # new logo
        self.assertNotIn('src="/static/images/logo.png"', html)  # old logo gone
        self.assertNotIn("Packed", html)                     # fake step gone
        self.assertIn("Production sync pending", html)       # honest state
        self.assertIn("ocTimeline", html)
        self.assertIn("data-status-url", html)               # polling wired
        self.assertIn("Shipping", html)                      # real totals rows


class EmailIdempotencyTests(TestCase):
    def test_order_paid_event_deduped(self):
        from notifications.notify import notify_order_event
        from notifications import events as ev
        from notifications.models import OutboundEvent
        o, _ = _mk_order()
        with override_settings(N8N_ENABLED=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            notify_order_event(o, ev.ORDER_PAID)
            notify_order_event(o, ev.ORDER_PAID)             # reconciliation double-fire
            notify_order_event(o, ev.ORDER_PAID)
        self.assertEqual(OutboundEvent.objects.filter(order=o, event_type=ev.ORDER_PAID).count(), 1)

    def test_failed_event_can_retry(self):
        from notifications.notify import notify_order_event
        from notifications import events as ev
        from notifications.models import OutboundEvent
        o, _ = _mk_order(order_number="T-OC-2", payment_id="CAP-T2")
        with override_settings(N8N_ENABLED=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            notify_order_event(o, ev.ORDER_PAID)
        OutboundEvent.objects.filter(order=o).update(status=OutboundEvent.STATUS_FAILED)
        with override_settings(N8N_ENABLED=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            notify_order_event(o, ev.ORDER_PAID)             # retry allowed after failure
        self.assertEqual(OutboundEvent.objects.filter(order=o, event_type=ev.ORDER_PAID).count(), 2)
