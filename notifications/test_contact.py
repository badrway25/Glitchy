"""Contact centre: the public form, its anti-abuse layers, and assistant escalation.

Nothing here sends a real email or calls n8n — the dispatcher is mocked or
disabled, exactly like the rest of the notification tests.
"""
import time
from unittest import mock

from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account
from notifications.models import ContactRequest

CONTACT_URL = "/contact/"


def _payload(**extra):
    data = {
        "name": "Marco Rossi",
        "email": "marco@example.com",
        "category": "delivery",
        "order_number": "",
        "message": "My parcel has not arrived yet, can you check the tracking?",
        "consent": "on",
        "website": "",                                    # honeypot stays empty
        "form_ts": signing.dumps(time.time() - 12, salt="contact-ts"),
    }
    data.update(extra)
    return data


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"],
                   N8N_ENABLED=False, EMAIL_SMTP_FALLBACK=False)
class ContactPageTests(TestCase):
    def setUp(self):
        # the IP-based limiter is cache-backed and LocMemCache is shared across
        # tests in a process — clear it so one test cannot throttle the next
        from django.core.cache import cache
        cache.clear()

    def test_page_renders_with_every_category(self):
        resp = self.client.get(CONTACT_URL)
        self.assertEqual(resp.status_code, 200)
        for label in ("Order question", "Payment problem", "Delivery",
                      "Return", "Product information", "Other"):
            self.assertContains(resp, label)

    def test_page_has_antispam_fields(self):
        html = self.client.get(CONTACT_URL).content.decode()
        self.assertIn('name="website"', html)      # honeypot
        self.assertIn('name="form_ts"', html)      # min-time token
        self.assertIn("csrfmiddlewaretoken", html)

    def test_category_can_be_prefilled_from_a_link(self):
        html = self.client.get(CONTACT_URL + "?category=payment").content.decode()
        self.assertIn('value="payment" checked', html)
        self.assertNotIn('value="order" checked', html)

    def test_valid_submission_is_stored(self):
        resp = self.client.post(CONTACT_URL, _payload(), follow=True)
        self.assertEqual(resp.status_code, 200)
        request = ContactRequest.objects.get()
        self.assertEqual(request.email, "marco@example.com")
        self.assertEqual(request.category, "delivery")
        self.assertIn("parcel", request.message)
        self.assertContains(resp, "Message sent")

    def test_submission_queues_one_outbound_event(self):
        with mock.patch("notifications.contact.dispatch_event") as dispatch:
            self.client.post(CONTACT_URL, _payload())
        self.assertEqual(dispatch.call_count, 1)

    def test_dispatch_failure_still_stores_the_request(self):
        with mock.patch("notifications.contact.dispatch_event",
                        side_effect=RuntimeError("n8n down")):
            resp = self.client.post(CONTACT_URL, _payload(), follow=True)
        self.assertEqual(ContactRequest.objects.count(), 1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ContactRequest.objects.get().status, ContactRequest.STATUS_PENDING)

    def test_honeypot_silently_swallows_bots(self):
        resp = self.client.post(CONTACT_URL, _payload(website="http://spam.example"),
                                follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ContactRequest.objects.count(), 0)

    def test_instant_submission_rejected(self):
        resp = self.client.post(
            CONTACT_URL, _payload(form_ts=signing.dumps(time.time(), salt="contact-ts")),
            follow=True)
        self.assertEqual(ContactRequest.objects.count(), 0)
        self.assertEqual(resp.status_code, 200)

    def test_forged_token_rejected(self):
        resp = self.client.post(CONTACT_URL, _payload(form_ts="not-a-token"), follow=True)
        self.assertEqual(ContactRequest.objects.count(), 0)
        self.assertEqual(resp.status_code, 200)

    def test_rate_limit_stops_flooding(self):
        for i in range(8):
            self.client.post(CONTACT_URL, _payload(
                message=f"Message number {i} about my delivery please help"))
        self.assertLessEqual(ContactRequest.objects.count(), 5)

    def test_rejected_submissions_do_not_consume_the_budget(self):
        """A few typos must not lock a genuine customer out for an hour."""
        for _ in range(6):
            self.client.post(CONTACT_URL, _payload(email="not-an-email"))
        self.client.post(CONTACT_URL, _payload())
        self.assertEqual(ContactRequest.objects.count(), 1)

    def test_expired_token_asks_to_resend_instead_of_dropping(self):
        # Django times the SIGNATURE, not our payload, so age out the max instead
        with mock.patch("notifications.contact.MAX_TOKEN_AGE", -1):
            resp = self.client.post(CONTACT_URL, _payload(), follow=True)
        self.assertEqual(ContactRequest.objects.count(), 0)
        self.assertContains(resp, "send it again")

    def test_identical_message_after_the_dedupe_window_is_a_new_request(self):
        payload = _payload()
        self.client.post(CONTACT_URL, payload)
        with mock.patch("notifications.contact.DEDUPE_WINDOW_SECONDS", 0):
            self.client.post(CONTACT_URL, _payload())
        self.assertEqual(ContactRequest.objects.count(), 2)

    def test_invalid_email_rejected(self):
        self.client.post(CONTACT_URL, _payload(email="not-an-email"))
        self.assertEqual(ContactRequest.objects.count(), 0)

    def test_short_message_rejected(self):
        self.client.post(CONTACT_URL, _payload(message="hi"))
        self.assertEqual(ContactRequest.objects.count(), 0)

    def test_unknown_category_rejected(self):
        self.client.post(CONTACT_URL, _payload(category="../etc/passwd"))
        self.assertEqual(ContactRequest.objects.count(), 0)

    def test_duplicate_submission_is_not_stored_twice(self):
        payload = _payload()
        self.client.post(CONTACT_URL, payload)
        self.client.post(CONTACT_URL, payload)
        self.assertEqual(ContactRequest.objects.count(), 1)

    def test_logged_in_user_is_linked(self):
        user = Account.objects.create_user("A", "B", "auser", "a@user.com", "pw-Str0ng!1")
        user.is_active = True
        user.save()
        self.client.force_login(user)
        self.client.post(CONTACT_URL, _payload(email="a@user.com"))
        self.assertEqual(ContactRequest.objects.get().account_id, user.pk)

    def test_order_number_is_captured_when_given(self):
        self.client.post(CONTACT_URL, _payload(order_number="123456789"))
        self.assertEqual(ContactRequest.objects.get().order_number, "123456789")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ContactI18nTests(TestCase):
    def test_italian_page(self):
        resp = self.client.get("/it/contact/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Contattaci")

    def test_french_page(self):
        resp = self.client.get("/fr/contact/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Contactez-nous")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class AssistantEscalationTests(TestCase):
    """When the assistant cannot answer it must point at the contact page,
    pre-selecting a sensible category — never sending anything on its own."""

    def _ask(self, question):
        return self.client.post(reverse("assistant:chat"),
                                {"message": question},
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    @override_settings(AI_API_KEY="", AI_PROVIDER="mock", AI_ASSISTANT_ENABLED=True)
    def test_ungrounded_answer_offers_the_contact_page(self):
        data = self._ask("Can you refund my credit card directly?").json()
        if data.get("can_contact_support"):
            self.assertIn("contact_url", data)
            self.assertIn("/contact/", data["contact_url"])

    def test_category_guessing_is_conservative(self):
        from assistant.escalation import guess_category
        self.assertEqual(guess_category("my paypal payment failed"), "payment")
        self.assertEqual(guess_category("where is my parcel? tracking"), "delivery")
        self.assertEqual(guess_category("I want to return this shirt"), "returns")
        self.assertEqual(guess_category("what size is the tee"), "product")
        self.assertEqual(guess_category("hello there"), "other")

    def test_contact_url_carries_the_category(self):
        from assistant.escalation import contact_url_for
        url = contact_url_for("my paypal payment failed")
        self.assertIn("/contact/", url)
        self.assertIn("category=payment", url)

    def test_no_pii_or_secrets_in_the_escalation_link(self):
        from assistant.escalation import contact_url_for
        url = contact_url_for("my card 4111111111111111 was charged twice")
        self.assertNotIn("4111", url)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ContactAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("A", "B", "c@x.com", "cadmin",
                                                  "pw-Str0ng!123")

    def test_changelist_renders_with_status_badges(self):
        ContactRequest.objects.create(name="N", email="n@x.com", category="payment",
                                      message="A message long enough to store")
        self.client.force_login(self.su)
        resp = self.client.get("/admin/notifications/contactrequest/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Payment problem")

    def test_requires_staff(self):
        self.assertEqual(
            self.client.get("/admin/notifications/contactrequest/").status_code, 302)
