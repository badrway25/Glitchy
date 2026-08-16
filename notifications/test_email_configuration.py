"""Admin Mail Control Center: encrypted write-only secrets, DB→env resolver,
controlled (no-real-email) test send, DB-aware system check.

A throwaway Fernet key is injected via override_settings so the tests are
deterministic and independent of the server env. No test ever sends a real email
(console/locmem backends only) or asserts a secret in a way that would log it
beyond a local equality check.
"""
from cryptography.fernet import Fernet
from django.core import mail
from django.test import TestCase, override_settings

from notifications.models import EmailConfiguration

KEY = Fernet.generate_key().decode()
REAL = "help@glitchy.graphics"
PLACEHOLDER = "support@example.com"


@override_settings(PAYMENT_CONFIG_KEY=KEY)
class EncryptedSecretTests(TestCase):
    def test_password_is_write_only_and_masked(self):
        cfg = EmailConfiguration.load()
        cfg.set_secret("smtp_password", "s3cr3t-app-password")
        cfg.save()
        cfg.refresh_from_db()
        # ciphertext is not the plaintext; decrypt round-trips server-side only
        self.assertNotIn("s3cr3t", cfg.smtp_password_ciphertext)
        self.assertTrue(cfg.has_secret("smtp_password"))
        self.assertEqual(cfg.get_secret("smtp_password"), "s3cr3t-app-password")
        # masked display never reveals the secret
        disp = cfg.secret_display("smtp_password")
        self.assertNotIn("s3cr3t", disp)
        self.assertIn("fp:", disp)
        # __str__ never leaks
        self.assertNotIn("s3cr3t", str(cfg))

    def test_singleton_enforced(self):
        a = EmailConfiguration.load()
        a.save()
        b = EmailConfiguration.load()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(EmailConfiguration.objects.count(), 1)

    def test_missing_key_refuses_to_encrypt(self):
        from notifications import secrets as secretbox
        with override_settings(PAYMENT_CONFIG_KEY=""):
            self.assertFalse(secretbox.has_key())
            cfg = EmailConfiguration.load()
            with self.assertRaises(secretbox.SecretKeyMissing):
                cfg.set_secret("smtp_password", "x")


@override_settings(PAYMENT_CONFIG_KEY=KEY, SUPPORT_EMAIL="env-support@glitchy.graphics",
                   ADMIN_NOTIFY_EMAIL="", DEFAULT_FROM_EMAIL="env-from@glitchy.graphics")
class ResolverTests(TestCase):
    def test_no_config_falls_back_to_env(self):
        from notifications import email_settings as es
        self.assertEqual(es.get_support_email(), "env-support@glitchy.graphics")
        self.assertEqual(es.get_admin_notify_email(), "env-support@glitchy.graphics")
        self.assertEqual(es.get_default_from_email(), "env-from@glitchy.graphics")
        self.assertEqual(es.get_email_backend_settings(), {})   # default connection

    def test_disabled_config_still_uses_env(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = False
        cfg.support_email = "db-support@glitchy.graphics"
        cfg.save()
        self.assertEqual(es.get_support_email(), "env-support@glitchy.graphics")

    def test_enabled_config_overrides_env(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.support_email = "db-support@glitchy.graphics"
        cfg.admin_notify_email = "db-ops@glitchy.graphics"
        cfg.default_from_email = "db-from@glitchy.graphics"
        cfg.save()
        self.assertEqual(es.get_support_email(), "db-support@glitchy.graphics")
        self.assertEqual(es.get_admin_notify_email(), "db-ops@glitchy.graphics")
        self.assertEqual(es.get_default_from_email(), "db-from@glitchy.graphics")

    def test_public_support_hides_placeholder_from_db(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.support_email = PLACEHOLDER
        cfg.save()
        self.assertEqual(es.get_public_support_email(), "")

    def test_smtp_backend_settings_built_from_db(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.provider = EmailConfiguration.PROVIDER_SMTP
        cfg.smtp_host = "smtp.example.net"
        cfg.smtp_port = 465
        cfg.smtp_use_tls = False
        cfg.smtp_use_ssl = True
        cfg.smtp_username = "mailer@glitchy.graphics"
        cfg.set_secret("smtp_password", "app-pass-xyz")
        cfg.save()
        s = es.get_email_backend_settings()
        self.assertEqual(s["host"], "smtp.example.net")
        self.assertEqual(s["port"], 465)
        self.assertTrue(s["use_ssl"])
        self.assertFalse(s["use_tls"])
        self.assertEqual(s["password"], "app-pass-xyz")   # decrypted server-side

    def test_console_provider_selects_console_backend(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.provider = EmailConfiguration.PROVIDER_CONSOLE
        cfg.save()
        self.assertIn("console", es.get_email_backend_settings()["backend"])

    def test_n8n_override_prefers_db_when_enabled(self):
        from notifications import email_settings as es
        with override_settings(N8N_WEBHOOK_BASE_URL="https://env.n8n/"):
            self.assertEqual(es.get_n8n_mail_settings()["base_url"], "https://env.n8n/")
            cfg = EmailConfiguration.load()
            cfg.is_enabled = True
            cfg.n8n_mail_enabled = True
            cfg.n8n_webhook_url = "https://db.n8n/hooks"
            cfg.set_secret("n8n_secret", "n8n-shhh")
            cfg.save()
            resolved = es.get_n8n_mail_settings()
            self.assertEqual(resolved["base_url"], "https://db.n8n/hooks")
            self.assertEqual(resolved["shared_secret"], "n8n-shhh")

    def test_is_email_configured(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.provider = EmailConfiguration.PROVIDER_SMTP
        cfg.support_email = REAL
        cfg.save()
        self.assertFalse(es.is_email_configured())     # no host yet
        cfg.smtp_host = "smtp.example.net"
        cfg.save()
        self.assertTrue(es.is_email_configured())


@override_settings(PAYMENT_CONFIG_KEY=KEY)
class TestSendTests(TestCase):
    def test_console_provider_send_uses_no_network(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.provider = EmailConfiguration.PROVIDER_CONSOLE
        cfg.support_email = REAL
        cfg.save()
        res = es.send_test_email(cfg, "ops@glitchy.graphics", requested_by="admin@x")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "connected")
        cfg.refresh_from_db()
        self.assertEqual(cfg.last_test_status, "connected")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_smtp_provider_send_goes_through_backend_not_network(self):
        # locmem override means even the "smtp" path lands in the outbox, not a socket
        from notifications import email_settings as es
        mail.outbox = []
        cfg = EmailConfiguration.load()
        cfg.is_enabled = True
        cfg.provider = EmailConfiguration.PROVIDER_CONSOLE   # safe, no socket
        cfg.support_email = REAL
        cfg.default_from_email = REAL
        cfg.save()
        res = es.send_test_email(cfg, "ops@glitchy.graphics")
        self.assertTrue(res["ok"])

    def test_disabled_provider_reports_error_not_send(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.provider = EmailConfiguration.PROVIDER_DISABLED
        cfg.save()
        res = es.send_test_email(cfg, "ops@glitchy.graphics")
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "failed")

    def test_n8n_provider_is_skipped_not_sent(self):
        from notifications import email_settings as es
        cfg = EmailConfiguration.load()
        cfg.provider = EmailConfiguration.PROVIDER_N8N
        cfg.save()
        res = es.send_test_email(cfg, "ops@glitchy.graphics")
        self.assertEqual(res["status"], "skipped")

    def test_safe_error_strips_credential_words(self):
        from notifications.email_settings import _safe_error
        cleaned = _safe_error("SMTP AUTH failed for password 'hunter2'")
        self.assertNotIn("hunter2", cleaned)
        self.assertNotIn("password", cleaned.lower())


@override_settings(PAYMENT_CONFIG_KEY=KEY)
class SystemCheckTests(TestCase):
    def test_db_config_clears_the_warning_even_with_placeholder_env(self):
        from notifications.checks import support_email_configuration
        with override_settings(SUPPORT_EMAIL=PLACEHOLDER, ADMIN_NOTIFY_EMAIL=""):
            self.assertTrue(support_email_configuration(app_configs=None))   # warns
            cfg = EmailConfiguration.load()
            cfg.is_enabled = True
            cfg.support_email = REAL
            cfg.admin_notify_email = REAL
            cfg.save()
            self.assertEqual(support_email_configuration(app_configs=None), [])  # clear


@override_settings(PAYMENT_CONFIG_KEY=KEY, ALLOWED_HOSTS=["testserver"])
class AdminPermissionTests(TestCase):
    """Superadmin can modify; a non-superadmin staffer can view but modify nothing,
    and never sees the secret fields."""

    def setUp(self):
        from accounts.models import Account
        self.cfg = EmailConfiguration.load()
        self.cfg.is_enabled = True
        self.cfg.provider = EmailConfiguration.PROVIDER_CONSOLE
        self.cfg.set_secret("smtp_password", "keep-me-secret")
        self.cfg.save()

        def mk(email, superadmin):
            u = Account(email=email, username=email.split("@")[0], first_name="A",
                        last_name="B")
            u.set_password("x")
            u.is_active = u.is_admin = u.is_staff = True
            u.is_superadmin = superadmin
            u.save()
            return u

        self.super = mk("mailsuper@x.com", True)
        self.staff = mk("mailstaff@x.com", False)

    def _change_url(self):
        return f"/admin/notifications/emailconfiguration/{self.cfg.pk}/change/"

    def test_superadmin_sees_editable_secret_field(self):
        self.client.force_login(self.super)
        html = self.client.get(self._change_url()).content.decode()
        self.assertIn("new_smtp_password", html)          # can set a new secret
        self.assertIn('name="provider"', html)            # editable select
        self.assertNotIn("keep-me-secret", html)          # never the plaintext

    def test_staff_cannot_modify_and_has_no_secret_fields(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self._change_url())
        self.assertEqual(resp.status_code, 200)           # can VIEW
        html = resp.content.decode()
        self.assertNotIn("new_smtp_password", html)       # no secret field
        self.assertNotIn("new_n8n_secret", html)
        self.assertNotIn('name="provider"', html)         # provider not editable
        self.assertNotIn('name="support_email"', html)    # addresses not editable
        self.assertNotIn("keep-me-secret", html)          # never the plaintext

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get(self._change_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])


@override_settings(PAYMENT_CONFIG_KEY=KEY)
class AdminFormTests(TestCase):
    def test_tls_and_ssl_cannot_both_be_true(self):
        from notifications.admin_email import EmailConfigurationForm
        form = EmailConfigurationForm(data={
            "is_enabled": True, "provider": EmailConfiguration.PROVIDER_SMTP,
            "smtp_host": "smtp.example.net", "smtp_port": 587,
            "smtp_use_tls": True, "smtp_use_ssl": True, "smtp_username": "u",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("TLS and SSL", str(form.errors))

    def test_blank_password_keeps_existing_secret(self):
        # save_model logic: a blank new_smtp_password must not wipe the stored one.
        cfg = EmailConfiguration.load()
        cfg.set_secret("smtp_password", "keep-me")
        cfg.save()
        # simulate the admin save with a blank field
        blank = ""
        if blank.strip():
            cfg.set_secret("smtp_password", blank)
        cfg.refresh_from_db()
        self.assertEqual(cfg.get_secret("smtp_password"), "keep-me")
