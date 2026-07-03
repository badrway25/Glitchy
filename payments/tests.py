"""Payment Control Center — security + resolver + monitoring tests (Phase 76).

Payment provider APIs are MOCKED — no real charge, capture or refund is ever made, and no real
secret is used. Focus: secrets encrypted at rest + never leaked, superadmin gating, the
DB-preferred/env-fallback resolver, and the safe audit log.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from accounts.models import Account

TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
STRIPE_SECRET = "sk_test_SECRET_do_not_leak_9999"
WEBHOOK_SECRET = "whsec_SECRET_1234"
PAYPAL_SECRET = "ppSECRET_7777"


@override_settings(PAYMENT_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PaymentSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.staff = Account.objects.create_user("St", "Aff", "staff@x.com", "staff", "pw-Str0ng!123")
        cls.staff.is_staff = True; cls.staff.is_admin = True; cls.staff.is_active = True
        cls.staff.is_superadmin = False; cls.staff.save()

    def _stripe(self):
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig(provider="stripe", environment="test")
        c.set_secret("stripe_secret_key", STRIPE_SECRET, by="adm")
        c.set_secret("stripe_webhook_secret", WEBHOOK_SECRET, by="adm")
        c.save()
        return c

    def test_secret_encrypted_at_rest_not_plaintext(self):
        c = self._stripe()
        self.assertNotIn(STRIPE_SECRET, c.stripe_secret_key_ciphertext)
        self.assertTrue(c.stripe_secret_key_ciphertext)             # ciphertext stored
        self.assertEqual(c.get_secret("stripe_secret_key"), STRIPE_SECRET)   # decrypts server-side
        self.assertEqual(c.stripe_secret_key_last_four, "9999")

    def test_secret_never_in_change_form_html(self):
        c = self._stripe()
        self.client.force_login(self.su)
        html = self.client.get(f"/admin/payments/paymentproviderconfig/{c.id}/change/").content.decode()
        self.assertNotIn(STRIPE_SECRET, html)
        self.assertNotIn(WEBHOOK_SECRET, html)
        self.assertNotIn(TEST_KEY, html)
        self.assertIn("9999", html)                                 # masked last-4 shown

    def test_non_superadmin_cannot_see_secret_fields(self):
        c = self._stripe()
        self.client.force_login(self.staff)
        html = self.client.get(f"/admin/payments/paymentproviderconfig/{c.id}/change/").content.decode()
        self.assertNotIn("new_stripe_secret_key", html)
        self.assertNotIn(STRIPE_SECRET, html)

    def test_non_superadmin_cannot_test_connection(self):
        c = self._stripe()
        self.client.force_login(self.staff)
        resp = self.client.post(f"/admin/payments/paymentproviderconfig/{c.id}/test-connection/")
        self.assertEqual(resp.status_code, 403)

    def test_test_connection_is_readonly_no_charge(self):
        c = self._stripe()
        self.client.force_login(self.su)
        mock_stripe = MagicMock()
        mock_stripe.Account.retrieve.return_value = {"id": "acct_123", "charges_enabled": True}
        mock_stripe.Balance.retrieve.return_value = {"available": [{"currency": "eur"}]}
        with patch.dict("sys.modules", {"stripe": mock_stripe}):
            self.client.post(f"/admin/payments/paymentproviderconfig/{c.id}/test-connection/")
        # only read endpoints were touched — never a PaymentIntent/Charge/Refund
        called = [m[0] for m in mock_stripe.method_calls]
        for forbidden in ("PaymentIntent", "Charge", "Refund", "checkout"):
            self.assertFalse(any(forbidden in m for m in called), "called %s" % called)
        c.refresh_from_db()
        self.assertEqual(c.last_connection_status, "connected")

    def test_safe_defaults_off(self):
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig.objects.create(provider="stripe")
        self.assertFalse(c.is_enabled)
        self.assertFalse(c.allow_checkout)
        self.assertFalse(c.allow_live_mode)
        self.assertEqual(c.environment, "test")
        self.assertFalse(c.is_ready_for_checkout())


@override_settings(PAYMENT_CONFIG_KEY=TEST_KEY)
class ResolverTests(TestCase):
    def test_env_fallback_when_no_db_config(self):
        from payments import config as pc
        with override_settings(STRIPE_SECRET_KEY="sk_env", STRIPE_PUBLIC_KEY="pk_env"):
            self.assertEqual(pc.stripe_secret_key(), "sk_env")
            self.assertEqual(pc.stripe_source(), "env")

    def test_db_preferred_when_enabled(self):
        from payments import config as pc
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig(provider="stripe", is_enabled=True, environment="test")
        c.set_secret("stripe_secret_key", STRIPE_SECRET, by="adm"); c.save()
        with override_settings(STRIPE_SECRET_KEY="sk_env"):
            self.assertEqual(pc.stripe_secret_key(), STRIPE_SECRET)
            self.assertEqual(pc.stripe_source(), "db")

    def test_live_key_never_served_without_live_gate(self):
        from payments import config as pc
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig(provider="stripe", is_enabled=True, environment="live",
                                  allow_live_mode=False)
        c.set_secret("stripe_secret_key", "sk_live_x", by="adm"); c.save()
        with override_settings(STRIPE_SECRET_KEY="sk_env"):
            self.assertEqual(pc.stripe_secret_key(), "sk_env")      # falls back — live gate off


class CredentialFieldsUXTests(TestCase):
    """The owner's report: the add form showed no fields for the API keys."""

    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm2@x.com", "adm2", "pw-Str0ng!123")

    def test_add_form_shows_stripe_and_paypal_credential_fields(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/payments/paymentproviderconfig/add/").content.decode()
        for field in ("id_stripe_publishable_key", "id_new_stripe_secret_key",
                      "id_new_stripe_webhook_secret", "id_paypal_client_id",
                      "id_new_paypal_secret", "id_paypal_webhook_id"):
            self.assertIn(field, html, f"add form is missing {field}")

    def test_add_form_hides_non_editable_meta(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/payments/paymentproviderconfig/add/").content.decode()
        self.assertNotIn("field-created_at", html)
        self.assertNotIn("field-updated_at", html)
        self.assertNotIn("field-connection_state_detail", html)

    def test_environment_defaults_to_test_not_live(self):
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig.objects.create(provider="paypal")
        self.assertEqual(c.environment, "test")
        self.assertFalse(c.is_live())

    def test_capture_and_refund_gates_default_off(self):
        from payments.models import PaymentProviderConfig
        c = PaymentProviderConfig.objects.create(provider="stripe")
        self.assertFalse(c.allow_capture)
        self.assertFalse(c.allow_refund)


# NOTE: the F76B admin language-switcher / i18n-catalog tests were NOT ported here —
# those commits (86cc950, 3b013ed) are intentionally excluded from this integration
# (they conflict with 4 later i18n phases) and remain pending work.
