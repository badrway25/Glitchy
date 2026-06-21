"""Assistant guardrail + endpoint tests. They run WITHOUT calling any external
LLM: AI_API_KEY is blanked so the service uses the offline fallback (KB retrieval),
keeping tests deterministic and network-free."""
import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import AssistantMessage, KnowledgeEntry


@override_settings(AI_API_KEY="", AI_PROVIDER="mock", AI_ASSISTANT_ENABLED=True)
class AssistantGuardrailTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        KnowledgeEntry.objects.create(
            key="returns-window", category="returns", is_active=True,
            keywords="returns,return,reso,resi,retour",
            question="How do returns work?",
            answer="You can return your order within 14 days of delivery, free and easy.")
        KnowledgeEntry.objects.create(
            key="payments", category="payments", is_active=True,
            keywords="payment,pay,card,stripe,paypal",
            question="Which payment methods?",
            answer="We accept major cards via Stripe and PayPal.")

    def _ask(self, message):
        return self.client.post(reverse("assistant:chat"),
                                data=json.dumps({"message": message}),
                                content_type="application/json")

    def test_in_context_returns_grounded_answer(self):
        r = self._ask("What is your return policy?")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["grounded"])
        self.assertIn("14 days", data["answer"])

    def test_out_of_context_declines(self):
        r = self._ask("What is the capital of France and the weather there?")
        data = r.json()
        self.assertFalse(data["grounded"])
        self.assertTrue(data["can_contact_support"])
        self.assertIn("don't have enough information", data["answer"])

    def test_guest_gets_no_order_data(self):
        # A guest asking about "my order tracking" must never receive order details.
        r = self._ask("Where is my order tracking?")
        data = r.json()
        # falls back to KB/decline — never includes order numbers
        self.assertNotIn("Order #", data["answer"])

    def test_empty_message_rejected(self):
        r = self._ask("   ")
        self.assertEqual(r.status_code, 400)

    def test_input_is_capped(self):
        r = self._ask("returns " * 500)  # very long
        self.assertEqual(r.status_code, 200)  # truncated, not errored

    def test_chat_requires_post(self):
        r = self.client.get(reverse("assistant:chat"))
        self.assertEqual(r.status_code, 405)

    @override_settings(AI_RATE_LIMIT=3)
    def test_rate_limit(self):
        for _ in range(3):
            self.assertNotEqual(self._ask("returns?").status_code, 429)
        self.assertEqual(self._ask("returns?").status_code, 429)

    def test_suggestions_endpoint(self):
        r = self.client.get(reverse("assistant:suggestions"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["enabled"])
        self.assertTrue(len(r.json()["questions"]) >= 4)

    def test_feedback_endpoint(self):
        self._ask("returns?")
        msg = AssistantMessage.objects.filter(role="assistant").first()
        r = self.client.post(reverse("assistant:feedback"),
                             data=json.dumps({"message_id": msg.id, "helpful": True}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(msg.feedback.count(), 1)

    def test_support_handoff_creates_message(self):
        from notifications.models import SupportMessage
        r = self.client.post(reverse("assistant:support"),
                             data=json.dumps({"email": "x@example.com", "message": "help"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(SupportMessage.objects.filter(from_email="x@example.com").exists())


class RetrievalTests(TestCase):
    def test_keyword_retrieval(self):
        from .retrieval import retrieve_knowledge
        KnowledgeEntry.objects.create(key="shipping", category="shipping", is_active=True,
                                      keywords="shipping,delivery,spedizione",
                                      question="Shipping?", answer="3-6 days.")
        hits = retrieve_knowledge("how long is shipping and delivery")
        self.assertTrue(any(h.key == "shipping" for h in hits))

    def test_disabled_assistant_returns_503(self):
        with override_settings(AI_ASSISTANT_ENABLED=False):
            r = Client().post(reverse("assistant:chat"),
                              data=json.dumps({"message": "hi"}),
                              content_type="application/json")
            self.assertEqual(r.status_code, 503)
