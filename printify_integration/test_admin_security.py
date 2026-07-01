"""Security tests for the Premium Admin + Printify control center.

The Printify API token must be encrypted at rest and NEVER leak into the admin (form, list,
history), and dangerous switches must default OFF and be superadmin-only. These tests are the
safety net for the most sensitive area of the app.
"""
from django.test import TestCase, override_settings

from accounts.models import Account
from printify_integration.models import PrintifyAccountConfig

# A throwaway Fernet key for tests only (not a real secret).
TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
SECRET = "printify-TOKEN-DoNotLeak-9xZ"


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class TokenStorageTests(TestCase):
    def test_token_encrypted_at_rest(self):
        cfg = PrintifyAccountConfig(name="Primary", is_active=True, shop_id="1")
        cfg.set_token(SECRET, by="adm")
        cfg.save()
        cfg.refresh_from_db()
        self.assertTrue(cfg.has_token())
        self.assertNotIn(SECRET, cfg.token_ciphertext)          # encrypted
        self.assertNotEqual(cfg.token_ciphertext, SECRET)
        self.assertEqual(cfg.get_token(), SECRET)               # server-side roundtrip

    def test_display_is_masked_and_fingerprinted(self):
        cfg = PrintifyAccountConfig(name="P", is_active=True)
        cfg.set_token(SECRET, by="adm")
        self.assertTrue(cfg.token_display().startswith("••••"))
        self.assertNotIn(SECRET, cfg.token_display())
        self.assertEqual(len(cfg.token_fingerprint), 12)
        self.assertNotIn(SECRET, cfg.token_fingerprint)

    def test_dangerous_defaults_are_off(self):
        cfg = PrintifyAccountConfig.objects.create(name="P")
        self.assertFalse(cfg.sync_enabled)
        self.assertFalse(cfg.allow_product_publish)
        self.assertFalse(cfg.allow_order_creation)
        self.assertEqual(cfg.sync_mode, PrintifyAccountConfig.SYNC_MODE_DRY)

    @override_settings(PRINTIFY_CONFIG_KEY="")
    def test_no_key_blocks_token_encryption(self):
        from printify_integration.secrets import SecretKeyMissing
        cfg = PrintifyAccountConfig(name="P")
        with self.assertRaises(SecretKeyMissing):
            cfg.set_token(SECRET, by="adm")


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class AdminTokenLeakTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.staff = Account.objects.create_user("St", "Aff", "staff@x.com", "staff", "pw-Str0ng!123")
        cls.staff.is_staff = True
        cls.staff.is_admin = True
        cls.staff.is_superadmin = False
        cls.staff.save()
        cls.cfg = PrintifyAccountConfig(name="Primary", is_active=True, shop_id="9")
        cls.cfg.set_token(SECRET, by="adm")
        cls.cfg.save()

    def _base(self):
        return "/admin/printify_integration/printifyaccountconfig/"

    def test_change_form_never_leaks_token(self):
        self.client.force_login(self.su)
        html = self.client.get(self._base() + f"{self.cfg.id}/change/").content.decode()
        self.assertNotIn(SECRET, html)
        self.assertIn("password", html)                         # write-only field present
        self.assertIn(self.cfg.token_last_four, html)           # masked last-4 shown
        self.assertIn(self.cfg.token_fingerprint, html)         # safe fingerprint shown

    def test_changelist_never_leaks_token(self):
        self.client.force_login(self.su)
        self.assertNotIn(SECRET, self.client.get(self._base()).content.decode())

    def test_history_never_leaks_token(self):
        self.client.force_login(self.su)
        html = self.client.get(self._base() + f"{self.cfg.id}/history/").content.decode()
        self.assertNotIn(SECRET, html)

    def test_change_form_renders_with_connection_data(self):
        # regression: connection_state_detail once built a variable-length parts list against a
        # fixed 5-placeholder format string -> IndexError on a config with a prior connection.
        from django.utils import timezone
        self.cfg.last_connection_check_at = timezone.now()
        self.cfg.last_connection_status = "connected"
        self.cfg.last_connection_shop_name = "Glitchy Store"
        self.cfg.last_connection_product_count = 18
        self.cfg.save()
        self.client.force_login(self.su)
        resp = self.client.get(self._base() + f"{self.cfg.id}/change/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("connected", html)
        self.assertNotIn(SECRET, html)

    def test_non_superadmin_cannot_enter_token(self):
        self.client.force_login(self.staff)
        html = self.client.get(self._base() + f"{self.cfg.id}/change/").content.decode()
        self.assertNotIn('name="new_token"', html)

    def test_non_superadmin_cannot_edit_dangerous_flags(self):
        self.client.force_login(self.staff)
        html = self.client.get(self._base() + f"{self.cfg.id}/change/").content.decode()
        self.assertNotIn('name="allow_product_publish"', html)
        self.assertNotIn('name="allow_order_creation"', html)
        self.assertNotIn('name="sync_mode"', html)

    def test_staff_save_cannot_set_token(self):
        # even if a staff user POSTs a token, save_model ignores it (superadmin gate)
        self.client.force_login(self.staff)
        self.client.post(self._base() + f"{self.cfg.id}/change/", {
            "name": "Primary", "is_active": "on", "shop_id": "9", "new_token": "HACKER-TOKEN",
            "sync_interval_seconds": "1800", "sync_enabled": "",
        })
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.get_token(), SECRET)          # unchanged


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class AdminActionsAndDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")

    def test_admin_index_loads_unfold(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        self.assertIn("Glitchy Commerce Studio", html)

    def test_test_connection_no_token_is_safe(self):
        cfg = PrintifyAccountConfig.objects.create(name="Empty", is_active=True)  # no token
        from printify_integration.admin import PrintifyAccountConfigAdmin
        from django.contrib.admin.sites import site
        a = PrintifyAccountConfigAdmin(PrintifyAccountConfig, site)

        class _Req:
            def __init__(self, u): self.user = u; self._messages = None
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        req = RequestFactory().get("/")
        req.user = self.su
        setattr(req, "session", "s")
        req._messages = FallbackStorage(req)
        a._test_one(req, cfg)
        cfg.refresh_from_db()
        self.assertEqual(cfg.last_connection_status, "failed")
        self.assertEqual(cfg.last_connection_error_safe, "No token set")


class CatalogHealthTests(TestCase):
    def test_catalog_health_check_safe_output(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("catalog_health_check", "--json", "--safe-output", stdout=out)
        text = out.getvalue()
        self.assertIn("health_score", text)
        for bad in ["token", "Bearer", "@", "password", "sk-"]:
            self.assertNotIn(bad, text)                         # no secret / PII
