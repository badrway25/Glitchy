import json

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from notifications import events as ev
from notifications.dispatcher import (
    compute_signature,
    dispatch_event,
    verify_signature,
)
from notifications.inbound import ingest_incoming_email
from notifications.models import OutboundEvent, SupportMessage
from orders.models import Order


class HmacTests(TestCase):
    def test_sign_and_verify_roundtrip(self):
        body = b'{"hello":"world"}'
        sig = compute_signature("secret", body)
        self.assertTrue(verify_signature("secret", body, sig))

    def test_wrong_secret_fails(self):
        body = b"data"
        sig = compute_signature("secret", body)
        self.assertFalse(verify_signature("other", body, sig))

    def test_empty_signature_fails(self):
        self.assertFalse(verify_signature("secret", b"x", ""))


@override_settings(
    N8N_ENABLED=False, EMAIL_SMTP_FALLBACK=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="shop@example.com",
)
class DispatchFallbackTests(TestCase):
    def test_disabled_n8n_uses_smtp_fallback(self):
        mail.outbox = []
        event = dispatch_event(
            ev.ORDER_PAID,
            {"order_number": "X1", "first_name": "Mara", "items": [], "items_subtotal": 0,
             "shipping_cost": 0, "tax": 0, "order_total": 0},
            recipient_email="cust@example.com", language="en",
        )
        self.assertEqual(event.status, OutboundEvent.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("X1", mail.outbox[0].subject)

    def test_internal_event_no_email_when_no_recipient(self):
        mail.outbox = []
        event = dispatch_event(ev.PRINTIFY_ERROR, {"subject": "boom"}, recipient_email="")
        self.assertEqual(event.status, OutboundEvent.STATUS_SKIPPED)
        self.assertEqual(len(mail.outbox), 0)


class InboundIngestTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            order_number="20250101999", first_name="Luc", last_name="B", phone="1",
            email="luc@example.com", address_line_1="x", country="FR", state="s", city="c",
            order_total=10.0, tax=0.0, is_ordered=True,
        )

    def test_dedup_by_message_id(self):
        payload = {"from_email": "a@b.com", "subject": "Hi", "message_id": "abc"}
        msg1, created1 = ingest_incoming_email(payload)
        msg2, created2 = ingest_incoming_email(payload)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(msg1.id, msg2.id)
        self.assertEqual(SupportMessage.objects.count(), 1)

    def test_links_order_from_subject(self):
        msg, _ = ingest_incoming_email({
            "from_email": "luc@example.com",
            "subject": "Problem with order 20250101999",
            "message_id": "m2",
        })
        self.assertEqual(msg.order_id, self.order.id)


@override_settings(N8N_SHARED_SECRET="topsecret")
class InboundApiAuthTests(TestCase):
    def test_missing_signature_401(self):
        resp = self.client.post(
            reverse("n8n_incoming_email"),
            data=json.dumps({"from_email": "a@b.com"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_valid_signature_accepted(self):
        body = json.dumps({"from_email": "a@b.com", "subject": "hello", "message_id": "z9"})
        sig = compute_signature("topsecret", body.encode("utf-8"))
        resp = self.client.post(
            reverse("n8n_incoming_email"), data=body,
            content_type="application/json", HTTP_X_SIGNATURE=sig,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
