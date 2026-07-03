"""Secure payment-provider configuration (Stripe / PayPal) + a lightweight audit log.

Mirrors the Printify secure-config pattern: server secrets are Fernet-encrypted at rest
(``PAYMENT_CONFIG_KEY``), write-only, never rendered — only a masked last-4 + fingerprint are
shown. Safe defaults: every provider ships DISABLED, in TEST mode, with checkout/live OFF until
a superuser explicitly turns them on. Public/publishable keys (already browser-exposed) are
stored in plaintext.
"""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import secrets as secretbox

# Each encrypted secret is stored as a 4-field slot: <name>_ciphertext / _fingerprint /
# _last_four / _set_at. This tuple drives the generic set/get/display helpers below.
_SECRET_SLOTS = {
    "stripe_secret_key": _("Stripe secret key"),
    "stripe_webhook_secret": _("Stripe webhook signing secret"),
    "paypal_secret": _("PayPal client secret"),
}


class PaymentProviderConfig(models.Model):
    """One row per payment provider. Secrets encrypted at rest, write-only in the admin."""

    STRIPE = "stripe"
    PAYPAL = "paypal"
    PROVIDER_CHOICES = [(STRIPE, "Stripe"), (PAYPAL, "PayPal")]

    ENV_TEST = "test"
    ENV_LIVE = "live"
    ENV_CHOICES = [(ENV_TEST, _("Test / sandbox")), (ENV_LIVE, _("Live"))]

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, unique=True)
    display_name = models.CharField(max_length=80, blank=True, default="")
    is_enabled = models.BooleanField(default=False, help_text=_("Use this config for checkout. OFF by default."))
    environment = models.CharField(max_length=10, choices=ENV_CHOICES, default=ENV_TEST)
    currency = models.CharField(max_length=8, blank=True, default="")

    # --- public / publishable (NOT secret — already exposed to the browser) ---
    stripe_publishable_key = models.CharField(max_length=255, blank=True, default="")
    paypal_client_id = models.CharField(max_length=255, blank=True, default="")
    paypal_api_base = models.CharField(max_length=120, blank=True, default="",
                                       help_text=_("Leave blank to derive from the environment."))

    # --- encrypted secret slots (write-only; never rendered) ---
    stripe_secret_key_ciphertext = models.TextField(blank=True, default="", editable=False)
    stripe_secret_key_fingerprint = models.CharField(max_length=16, blank=True, default="", editable=False)
    stripe_secret_key_last_four = models.CharField(max_length=8, blank=True, default="", editable=False)
    stripe_secret_key_set_at = models.DateTimeField(null=True, blank=True, editable=False)

    stripe_webhook_secret_ciphertext = models.TextField(blank=True, default="", editable=False)
    stripe_webhook_secret_fingerprint = models.CharField(max_length=16, blank=True, default="", editable=False)
    stripe_webhook_secret_last_four = models.CharField(max_length=8, blank=True, default="", editable=False)
    stripe_webhook_secret_set_at = models.DateTimeField(null=True, blank=True, editable=False)

    paypal_secret_ciphertext = models.TextField(blank=True, default="", editable=False)
    paypal_secret_fingerprint = models.CharField(max_length=16, blank=True, default="", editable=False)
    paypal_secret_last_four = models.CharField(max_length=8, blank=True, default="", editable=False)
    paypal_secret_set_at = models.DateTimeField(null=True, blank=True, editable=False)

    secret_updated_by = models.CharField(max_length=150, blank=True, default="", editable=False)

    # --- safety gates (superadmin only) ---
    allow_checkout = models.BooleanField(default=False, help_text=_("Superuser only. Keep OFF until tested."))
    allow_live_mode = models.BooleanField(default=False, help_text=_("Superuser only. Required to use live keys."))

    # --- connection status (safe, no secret) ---
    last_connection_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_connection_status = models.CharField(max_length=20, blank=True, default="", editable=False)
    last_connection_error_safe = models.CharField(max_length=200, blank=True, default="", editable=False)
    last_connection_detail_safe = models.CharField(max_length=300, blank=True, default="", editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Payment provider")
        verbose_name_plural = _("Payment providers")
        ordering = ["provider"]

    def __str__(self):
        return f"{self.get_provider_display()} ({self.get_environment_display()})"

    # -- encrypted-secret helpers (write-only) --------------------------------
    def set_secret(self, name, plaintext, by=""):
        """Encrypt + store a secret slot. Raises SecretKeyMissing if no PAYMENT_CONFIG_KEY."""
        if name not in _SECRET_SLOTS:
            raise KeyError(name)
        plaintext = (plaintext or "").strip()
        setattr(self, f"{name}_ciphertext", secretbox.encrypt(plaintext) if plaintext else "")
        setattr(self, f"{name}_fingerprint", secretbox.fingerprint(plaintext))
        setattr(self, f"{name}_last_four", secretbox.last_four(plaintext))
        setattr(self, f"{name}_set_at", timezone.now() if plaintext else None)
        if by:
            self.secret_updated_by = str(by)[:150]

    def get_secret(self, name):
        """Decrypt a secret slot (server-side only — never render)."""
        return secretbox.decrypt(getattr(self, f"{name}_ciphertext", ""))

    def has_secret(self, name):
        return bool(getattr(self, f"{name}_ciphertext", ""))

    def secret_display(self, name):
        """Masked representation for the admin — never the real secret."""
        lf = getattr(self, f"{name}_last_four", "")
        fp = getattr(self, f"{name}_fingerprint", "")
        if not self.has_secret(name):
            return "—"
        return f"•••• {lf}  ·  fp:{fp}" if lf else f"set  ·  fp:{fp}"

    # -- capability / readiness ----------------------------------------------
    def is_live(self):
        return self.environment == self.ENV_LIVE

    def is_ready_for_checkout(self):
        """A provider can serve checkout only when enabled, has its secret, and (for live) the
        live-mode gate is explicitly on."""
        if not (self.is_enabled and self.allow_checkout):
            return False
        if self.is_live() and not self.allow_live_mode:
            return False
        if self.provider == self.STRIPE:
            return self.has_secret("stripe_secret_key")
        if self.provider == self.PAYPAL:
            return bool(self.paypal_client_id and self.has_secret("paypal_secret"))
        return False

    @classmethod
    def for_provider(cls, provider):
        return cls.objects.filter(provider=provider).first()


class PaymentEvent(models.Model):
    """Safe audit log of payment operations (no secrets, no card data, no full PII).

    Closes the biggest gap found in the audit: there was no queryable trail of webhook
    deliveries / verification outcomes / refunds. Idempotent on external_id."""

    KIND_TEST = "test_connection"
    KIND_WEBHOOK = "webhook"
    KIND_VERIFY = "verify"
    KIND_REFUND = "refund"
    KIND_FINALIZE = "finalize"
    KIND_CHOICES = [
        (KIND_TEST, _("Test connection")), (KIND_WEBHOOK, _("Webhook")),
        (KIND_VERIFY, _("Verify capture")), (KIND_REFUND, _("Refund")),
        (KIND_FINALIZE, _("Finalize")),
    ]

    provider = models.CharField(max_length=20, choices=PaymentProviderConfig.PROVIDER_CHOICES)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    external_id = models.CharField(max_length=120, blank=True, default="", db_index=True,
                                   help_text=_("Provider event/charge id — idempotency key."))
    order_number = models.CharField(max_length=40, blank=True, default="")
    payment_id = models.CharField(max_length=120, blank=True, default="")
    ok = models.BooleanField(default=True)
    status = models.CharField(max_length=40, blank=True, default="")
    reason_safe = models.CharField(max_length=200, blank=True, default="")
    amount = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Payment event")
        verbose_name_plural = _("Payment monitor")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider}:{self.kind} {'ok' if self.ok else 'fail'}"

    @classmethod
    def log(cls, provider, kind, *, ok=True, external_id="", order_number="", payment_id="",
            status="", reason_safe="", amount=None, currency=""):
        """Idempotent-ish safe logger; never raises into the caller."""
        try:
            if external_id and cls.objects.filter(external_id=external_id, kind=kind).exists():
                return None
            return cls.objects.create(
                provider=provider, kind=kind, ok=ok, external_id=external_id[:120],
                order_number=str(order_number)[:40], payment_id=str(payment_id)[:120],
                status=str(status)[:40], reason_safe=str(reason_safe)[:200],
                amount=amount, currency=str(currency)[:8])
        except Exception:
            return None
