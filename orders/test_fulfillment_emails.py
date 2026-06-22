"""P0.2: shipped / in-production / tracking emails fire on status transition."""
from django.test import TestCase, override_settings
from orders.models import Order
from notifications.models import OutboundEvent


def _order(num="FF1", **kw):
    d = dict(first_name="A", last_name="B", phone="1", email="c@x.com", address_line_1="x",
             city="c", state="s", country="IT", order_total=20, tax=0, ip="1",
             order_number=num, is_ordered=True, language_code="en")
    d.update(kw)
    return Order.objects.create(**d)


@override_settings(N8N_ENABLED=False, EMAIL_SMTP_FALLBACK=False)  # record event, don't actually send
class FulfillmentNotifyTests(TestCase):
    def test_in_production_event_fires(self):
        from orders.fulfillment_notify import notify_fulfillment_transition
        o = _order("FF1")
        notify_fulfillment_transition(o, "", "in-production")
        self.assertTrue(OutboundEvent.objects.filter(event_type="order.in_production", order=o).exists())

    def test_shipped_event_fires(self):
        from orders.fulfillment_notify import notify_fulfillment_transition
        o = _order("FF2")
        notify_fulfillment_transition(o, "in-production", "fulfilled")
        self.assertTrue(OutboundEvent.objects.filter(event_type="order.shipped", order=o).exists())

    def test_tracking_event_only_when_number_present(self):
        from orders.fulfillment_notify import notify_fulfillment_transition
        o = _order("FF3", tracking_number="TRACK123")
        notify_fulfillment_transition(o, "fulfilled", "fulfilled", tracking_added=True)
        self.assertTrue(OutboundEvent.objects.filter(event_type="order.tracking_available", order=o).exists())

    def test_no_event_without_transition(self):
        from orders.fulfillment_notify import notify_fulfillment_transition
        o = _order("FF4")
        notify_fulfillment_transition(o, "fulfilled", "fulfilled")   # no change, no tracking
        self.assertEqual(OutboundEvent.objects.filter(order=o).count(), 0)

    def test_never_raises_on_bad_input(self):
        from orders.fulfillment_notify import notify_fulfillment_transition
        notify_fulfillment_transition(None, None, None)   # must not raise
