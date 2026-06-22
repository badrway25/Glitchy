"""Phase 28: email/n8n delivery readiness (mocked n8n + locmem SMTP — no real email)."""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from notifications.dispatcher import dispatch_event
from notifications.models import OutboundEvent


def _payload():
    return {"order_number": "EM1", "first_name": "A", "currency": "EUR"}


@override_settings(N8N_ENABLED=False, EMAIL_SMTP_FALLBACK=True,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SmtpFallbackTests(TestCase):
    def test_order_paid_delivers_via_smtp_when_n8n_off(self):
        mail.outbox = []
        ev = dispatch_event("order.paid", _payload(), recipient_email="buyer@example.com",
                            language="en")
        self.assertEqual(ev.status, OutboundEvent.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("buyer@example.com", mail.outbox[0].to)

    def test_shipped_and_tracking_and_returns_have_templates(self):
        mail.outbox = []
        for etype in ("order.shipped", "order.tracking_available", "return.requested",
                      "return.approved", "return.rejected", "refund.completed"):
            dispatch_event(etype, _payload(), recipient_email="b@example.com", language="it")
        # every event rendered + sent via the SMTP fallback (no template errors)
        self.assertEqual(len(mail.outbox), 6)


@override_settings(N8N_ENABLED=True, EMAIL_SMTP_FALLBACK=True,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class N8nDispatchTests(TestCase):
    def test_n8n_success_marks_sent(self):
        with patch("notifications.dispatcher._post_to_n8n", return_value=(True, 200, "")):
            ev = dispatch_event("order.paid", _payload(), recipient_email="b@example.com")
        self.assertEqual(ev.status, OutboundEvent.STATUS_SENT)

    @override_settings(N8N_MAX_RETRIES=1)   # exhaust retries on the first failure
    def test_n8n_failure_recovers_via_smtp(self):
        mail.outbox = []
        with patch("notifications.dispatcher._post_to_n8n", return_value=(False, 500, "boom")):
            ev = dispatch_event("order.paid", _payload(), recipient_email="b@example.com")
        # n8n failed (retries exhausted) but recovered through SMTP fallback -> delivered
        self.assertEqual(ev.status, OutboundEvent.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)

    def test_n8n_failure_with_retries_left_stays_retrying(self):
        # default N8N_MAX_RETRIES=3 -> a single failure is RETRYING, not yet SMTP-fallback
        with patch("notifications.dispatcher._post_to_n8n", return_value=(False, 500, "boom")):
            ev = dispatch_event("order.paid", _payload(), recipient_email="b@example.com")
        self.assertEqual(ev.status, OutboundEvent.STATUS_RETRYING)

    def test_event_is_always_persisted(self):
        with patch("notifications.dispatcher._post_to_n8n", return_value=(False, 0, "net")):
            ev = dispatch_event("order.paid", _payload(), recipient_email="")
        self.assertIsNotNone(ev.pk)   # record exists even with no recipient
