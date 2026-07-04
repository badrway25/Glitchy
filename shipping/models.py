"""Checkout intelligence config — Google Maps/Places + Address Validation, admin-managed.

Mirrors the Payment Control Center security model (payments app):
- The **browser key** (Places Autocomplete JS) is inherently public — Google requires it in the
  page and it must be referrer-restricted in the Google console. Stored in plaintext, like the
  Stripe publishable key.
- The **server key** (Address Validation API) is a real secret: Fernet-encrypted at rest via
  ``payments.secrets`` (same ``PAYMENT_CONFIG_KEY`` — documented on the field), write-only in
  the admin, only a masked ``•••• 1234 · fp:…`` is ever shown.
Safe defaults: everything OFF until a superadmin enables it; checkout NEVER depends on these —
when disabled/unconfigured the form is plain manual entry.
"""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payments import secrets as secretbox


class CheckoutApiConfig(models.Model):
    """Singleton-style config (use .load()). No orders, payments or mutations ever pass
    through these APIs — autocomplete suggestions + read-only address checks only."""

    is_enabled = models.BooleanField(
        default=False, help_text=_("Master switch. OFF = plain manual address entry."))
    enable_autocomplete = models.BooleanField(
        default=False, help_text=_("Load Google Places Autocomplete on the checkout address field."))
    enable_address_validation = models.BooleanField(
        default=False, help_text=_("Server-side Google Address Validation (used by the mode below)."))

    MODE_DISABLED, MODE_WARNING, MODE_STRICT = "disabled", "warning", "strict"
    validation_mode = models.CharField(
        max_length=10, default=MODE_DISABLED,
        choices=[(MODE_DISABLED, _("Disabled — manual entry, local checks only")),
                 (MODE_WARNING, _("Warning — unverified addresses need an explicit confirmation")),
                 (MODE_STRICT, _("Strict — only Google-verified addresses can order"))],
        help_text=_("How hard to enforce address verification at checkout. Strict needs Google "
                    "configured; it degrades to Warning if neither key is usable."))

    # public, referrer-restricted browser key (like a publishable key)
    maps_browser_key = models.CharField(
        max_length=100, blank=True, default="",
        help_text=_("Places JS browser key — public by design; restrict it by referrer in the "
                    "Google console. Never use a server key here."))
    allowed_domains_note = models.CharField(
        max_length=200, blank=True, default="",
        help_text=_("Reminder of the referrer restrictions configured in the Google console."))

    # encrypted server key (Address Validation API) — write-only slot
    server_key_ciphertext = models.TextField(blank=True, default="", editable=False)
    server_key_fingerprint = models.CharField(max_length=16, blank=True, default="", editable=False)
    server_key_last_four = models.CharField(max_length=8, blank=True, default="", editable=False)
    server_key_set_at = models.DateTimeField(null=True, blank=True, editable=False)
    secret_updated_by = models.CharField(max_length=150, blank=True, default="", editable=False)

    # safe connection status
    last_connection_status = models.CharField(max_length=20, blank=True, default="", editable=False)
    last_connection_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_connection_detail_safe = models.CharField(max_length=300, blank=True, default="", editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Checkout API settings")
        verbose_name_plural = _("Checkout API settings")

    def __str__(self):
        return "Google checkout APIs"

    # -- encrypted server-key helpers (write-only) --
    def set_server_key(self, plaintext, by=""):
        plaintext = (plaintext or "").strip()
        self.server_key_ciphertext = secretbox.encrypt(plaintext) if plaintext else ""
        self.server_key_fingerprint = secretbox.fingerprint(plaintext)
        self.server_key_last_four = secretbox.last_four(plaintext)
        self.server_key_set_at = timezone.now() if plaintext else None
        if by:
            self.secret_updated_by = str(by)[:150]

    def get_server_key(self):
        return secretbox.decrypt(self.server_key_ciphertext)

    def has_server_key(self):
        return bool(self.server_key_ciphertext)

    def server_key_display(self):
        if not self.has_server_key():
            return "—"
        return f"•••• {self.server_key_last_four}  ·  fp:{self.server_key_fingerprint}"

    # -- capability checks used by templates/services --
    def autocomplete_ready(self):
        return bool(self.is_enabled and self.enable_autocomplete and self.maps_browser_key)

    def validation_ready(self):
        return bool(self.is_enabled and self.enable_address_validation and self.has_server_key())

    def record_connection(self, status, detail=""):
        self.last_connection_status = status
        self.last_connection_check_at = timezone.now()
        self.last_connection_detail_safe = (detail or "")[:300]
        self.save(update_fields=["last_connection_status", "last_connection_check_at",
                                 "last_connection_detail_safe"])

    @classmethod
    def load(cls):
        return cls.objects.first()
