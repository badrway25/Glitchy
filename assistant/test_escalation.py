"""F6: the assistant must always offer a Contact-support CTA for support-sensitive
intents (payment / order / delivery / returns / complaints) — even when it produced
a "grounded" answer — and must not dangle product cards under a complaint.
"""
import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .escalation import (SUPPORT_SENSITIVE_CATEGORIES, contact_url_for,
                         guess_category, is_support_sensitive)
from .models import AssistantConversation, KnowledgeEntry
from .services import _finalise


class IntentDetectorTests(TestCase):
    def test_support_sensitive_categories(self):
        self.assertTrue(is_support_sensitive("I was charged twice, need a refund"))
        self.assertTrue(is_support_sensitive("where is my order? not arrived"))
        self.assertTrue(is_support_sensitive("I want to return this item"))
        self.assertTrue(is_support_sensitive("tracking for my parcel"))
        self.assertTrue(is_support_sensitive("il pagamento è fallito"))
        self.assertTrue(is_support_sensitive("où est ma commande"))

    def test_generic_complaint_is_support_sensitive_even_if_uncategorised(self):
        self.assertTrue(is_support_sensitive("this is broken and I have a problem"))
        self.assertTrue(is_support_sensitive("my package is damaged"))

    def test_browsing_and_greetings_are_not_support_sensitive(self):
        self.assertFalse(is_support_sensitive("hello"))
        self.assertFalse(is_support_sensitive("what colours does the tee come in"))
        self.assertFalse(is_support_sensitive(""))

    def test_categories_match_contact_form_values(self):
        self.assertEqual(guess_category("charged twice refund"), "payment")
        self.assertEqual(guess_category("where is my order"), "delivery")
        self.assertEqual(guess_category("I want a return"), "returns")
        self.assertIn("category=payment", contact_url_for("I was charged twice"))
        # never leak the shopper's words into the URL
        self.assertNotIn("charged", contact_url_for("I was charged twice"))
        self.assertTrue(SUPPORT_SENSITIVE_CATEGORIES <= {"payment", "delivery",
                                                         "returns", "order"})


class FinaliseEscalationTests(TestCase):
    def setUp(self):
        self.conv = AssistantConversation.objects.create(session_key="s-escal")

    def test_grounded_payment_answer_still_offers_contact(self):
        out = _finalise(self.conv, "We accept cards via Stripe and PayPal.",
                        "mock", grounded=True, sources=[], products=None,
                        question="I was charged twice, I need a refund now")
        self.assertTrue(out["can_contact_support"])
        self.assertIn("category=payment", out["contact_url"])
        self.assertEqual(out["contact_category"], "payment")

    def test_no_product_cards_under_a_complaint(self):
        from store.models import Product
        from category.models import Category
        cat, _ = Category.objects.get_or_create(category_name="T", slug="t")
        p = Product.objects.create(product_name="Tee", slug="tee", price=25,
                                   stock=5, category=cat, is_available=True)
        out = _finalise(self.conv, "Here is some help.", "mock", grounded=True,
                        sources=[], products=[p],
                        question="my order never arrived, this is a problem")
        self.assertTrue(out["can_contact_support"])
        self.assertNotIn("products", out)          # tone: no recommendations here

    def test_grounded_product_question_does_not_force_escalation(self):
        from store.models import Product
        from category.models import Category
        cat, _ = Category.objects.get_or_create(category_name="T", slug="t")
        p = Product.objects.create(product_name="Tee", slug="tee2", price=25,
                                   stock=5, category=cat, is_available=True)
        out = _finalise(self.conv, "It comes in black and white.", "mock",
                        grounded=True, sources=[], products=[p],
                        question="what colours does the tee come in")
        self.assertFalse(out["can_contact_support"])
        self.assertIn("products", out)             # browsing intent keeps suggestions

    def test_ungrounded_still_offers_contact(self):
        out = _finalise(self.conv, "I don't have enough information.", "mock",
                        grounded=False, sources=[], products=None,
                        question="what's the weather in Paris")
        self.assertTrue(out["can_contact_support"])


@override_settings(AI_API_KEY="", AI_PROVIDER="mock", AI_ASSISTANT_ENABLED=True)
class EndToEndEscalationTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        KnowledgeEntry.objects.create(
            key="payments", category="payments", is_active=True,
            keywords="payment,pay,card,stripe,paypal,charged,refund",
            question="Which payment methods?",
            answer="We accept major cards via Stripe and PayPal.")

    def _ask(self, message):
        return self.client.post(reverse("assistant:chat"),
                                data=json.dumps({"message": message}),
                                content_type="application/json")

    def test_payment_complaint_offers_payment_contact_and_no_placeholder_email(self):
        data = self._ask("I was charged twice and need a refund urgently").json()
        self.assertTrue(data["can_contact_support"])
        self.assertIn("category=payment", data.get("contact_url", ""))
        self.assertNotIn("products", data)
        self.assertNotIn("support@example.com", data.get("answer", ""))

    def test_order_question_offers_contact(self):
        data = self._ask("where is my order, it has not arrived").json()
        self.assertTrue(data["can_contact_support"])
        self.assertRegex(data.get("contact_url", ""), r"category=(order|delivery)")
