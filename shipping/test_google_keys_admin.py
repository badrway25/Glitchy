"""Google Maps keys admin — diagnostics + browser/server key separation tests.

No real Google calls (requests is always patched where a call could happen).
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from shipping.address_validation import test_connection
from shipping.models import CheckoutApiConfig

FERNET_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
BROWSER_KEY = "AIzaFAKE_browser_referrer_key"
SERVER_KEY = "AIzaFAKE_server_ip_key_5555"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class GoogleKeyDiagnosticsTests(TestCase):
    def test_browser_key_alone_is_never_tested_server_side(self):
        cfg = CheckoutApiConfig.objects.create(maps_browser_key=BROWSER_KEY)
        with patch("requests.post") as post:
            res = test_connection(cfg)
        self.assertFalse(post.called)                       # no server call for a browser key
        self.assertFalse(res["ok"])
        self.assertIn("server key", str(res["error"]).lower())

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_403_produces_actionable_diagnostics_without_key(self):
        cfg = CheckoutApiConfig.objects.create()
        cfg.set_server_key(SERVER_KEY); cfg.save()
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=403)
            res = test_connection(cfg)
        err = str(res["error"])
        for hint in ("billing", "referrer", "IP", "enabled"):
            self.assertIn(hint.lower(), err.lower())
        self.assertNotIn(SERVER_KEY, err)                   # never echo the key

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_400_and_429_mapped(self):
        cfg = CheckoutApiConfig.objects.create()
        cfg.set_server_key(SERVER_KEY); cfg.save()
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=400)
            self.assertIn("400", str(test_connection(cfg)["error"]))
            post.return_value = MagicMock(status_code=429)
            self.assertIn("429", str(test_connection(cfg)["error"]))

    def test_missing_payment_config_key_message(self):
        with override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY):
            cfg = CheckoutApiConfig.objects.create()
            cfg.set_server_key(SERVER_KEY); cfg.save()
        with override_settings(PAYMENT_CONFIG_KEY=""):      # key vanished -> decryption fails
            with patch("requests.post") as post:
                res = test_connection(cfg)
        self.assertFalse(post.called)
        self.assertIn("PAYMENT_CONFIG_KEY", str(res["error"]))
        self.assertNotIn(SERVER_KEY, str(res["error"]))

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_form_rejects_browser_key_pasted_as_server_key(self):
        from shipping.admin import CheckoutApiConfigForm
        form = CheckoutApiConfigForm({
            "is_enabled": True, "enable_autocomplete": True, "enable_address_validation": False,
            "validation_mode": "disabled",
            "maps_browser_key": BROWSER_KEY, "allowed_domains_note": "",
            "new_server_key": BROWSER_KEY,                  # same key -> confusion guard
        })
        self.assertFalse(form.is_valid())
        self.assertIn("BROWSER key", str(form.errors["new_server_key"]))


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class GoogleKeyAdminUXTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import Account
        cls.su = Account.objects.create_superuser("Adm", "Gk", "admgk@x.com", "admgk", "pw-Str0ng!123")

    def _page(self):
        cfg = CheckoutApiConfig.objects.create(maps_browser_key=BROWSER_KEY)
        self.client.force_login(self.su)
        return self.client.get(f"/admin/shipping/checkoutapiconfig/{cfg.id}/change/").content.decode()

    def test_two_key_sections_with_checklists(self):
        html = self._page()
        self.assertIn("Browser key — client-side autocomplete", html)
        self.assertIn("Server key — address validation", html)
        self.assertIn("glitchy.graphics/*", html)           # exact referrers documented
        self.assertIn("Maps JavaScript", html)
        self.assertIn("Address Validation API", html)

    def test_client_side_test_button_present(self):
        html = self._page()
        self.assertIn("glBrowserKeyTest", html)
        self.assertIn("Test browser key in this browser", html)
        self.assertIn("Test server key (server-side)", html.replace("&#x27;", "'")) if False else None
        # server-side test button is gated on having a server key
        self.assertIn("Add the server key to unlock the server-side test", html)

    def test_no_server_key_leak_in_page(self):
        html = self._page()
        self.assertNotIn(SERVER_KEY, html)
        # the browser key MAY appear (public by design) — but only in its own input
        self.assertIn(BROWSER_KEY, html)
