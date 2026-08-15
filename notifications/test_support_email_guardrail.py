"""F5: never show a placeholder support address to a customer, and warn (not block)
when the support/notification email is unconfigured.

SUPPORT_EMAIL falls back to `support@example.com` when the prod env is unset. The
guardrails: the assistant knowledge omits it, customer templates fall back to the
contact form, and `manage.py check` raises a non-blocking Warning.
"""
from django.core.checks import Warning as CheckWarning
from django.test import SimpleTestCase, TestCase, override_settings

from greatkart.support_email import (is_placeholder_email, public_support_email,
                                      support_email_configured)

REAL = "help@glitchy.graphics"
PLACEHOLDER = "support@example.com"
HOSTS = ["testserver", "127.0.0.1", "localhost"]


class HelperTests(SimpleTestCase):
    def test_placeholder_detection(self):
        for bad in ("", "   ", "not-an-email", PLACEHOLDER, "x@example.org",
                    "a@example.net"):
            self.assertTrue(is_placeholder_email(bad), bad)
        for good in (REAL, "team@shop.io", "hi@brand.co.uk"):
            self.assertFalse(is_placeholder_email(good), good)

    @override_settings(SUPPORT_EMAIL=PLACEHOLDER)
    def test_public_email_hidden_for_placeholder(self):
        self.assertEqual(public_support_email(), "")
        self.assertFalse(support_email_configured())

    @override_settings(SUPPORT_EMAIL=REAL)
    def test_public_email_shown_for_real(self):
        self.assertEqual(public_support_email(), REAL)
        self.assertTrue(support_email_configured())


class SystemCheckTests(SimpleTestCase):
    def _run(self):
        from notifications.checks import support_email_configuration
        return support_email_configuration(app_configs=None)

    @override_settings(SUPPORT_EMAIL=PLACEHOLDER, ADMIN_NOTIFY_EMAIL="")
    def test_warns_when_placeholder(self):
        results = self._run()
        ids = {w.id for w in results}
        self.assertIn("glitchy.support.W001", ids)
        self.assertIn("glitchy.support.W002", ids)
        self.assertTrue(all(isinstance(w, CheckWarning) for w in results))
        # never echo the address itself
        self.assertNotIn(PLACEHOLDER, " ".join(w.msg for w in results))

    @override_settings(SUPPORT_EMAIL=REAL, ADMIN_NOTIFY_EMAIL=REAL)
    def test_silent_when_configured(self):
        self.assertEqual(self._run(), [])


@override_settings(AI_API_KEY="", AI_PROVIDER="mock", AI_ASSISTANT_ENABLED=True)
class RetrievalKnowledgeTests(TestCase):
    @override_settings(SUPPORT_EMAIL=PLACEHOLDER)
    def test_placeholder_email_not_fed_to_the_model(self):
        from assistant.retrieval import store_facts
        facts = store_facts("how do I contact support")
        self.assertNotIn(PLACEHOLDER, facts)
        self.assertIn("/contact/", facts)

    @override_settings(SUPPORT_EMAIL=REAL)
    def test_real_email_is_available_to_the_model(self):
        from assistant.retrieval import store_facts
        self.assertIn(REAL, store_facts("contact support"))


@override_settings(ALLOWED_HOSTS=HOSTS)
class CustomerTemplateTests(TestCase):
    @override_settings(SUPPORT_EMAIL=PLACEHOLDER)
    def test_legal_pages_do_not_show_placeholder(self):
        for path in ("/privacy/", "/terms/", "/cookies/"):
            html = self.client.get(path).content.decode()
            self.assertNotIn(PLACEHOLDER, html, path)
            self.assertIn("/contact/", html, path)

    @override_settings(SUPPORT_EMAIL=PLACEHOLDER)
    def test_faq_falls_back_to_contact(self):
        html = self.client.get("/faq/").content.decode()
        self.assertNotIn("mailto:support@example.com", html)
        self.assertIn("/contact/", html)

    @override_settings(SUPPORT_EMAIL=REAL)
    def test_real_email_renders_mailto(self):
        html = self.client.get("/privacy/").content.decode()
        self.assertIn("mailto:" + REAL, html)
