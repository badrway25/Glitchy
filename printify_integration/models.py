from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PrintifyAccountConfig(models.Model):
    """Admin-managed Printify account + sync governance.

    Security: the API token is NEVER stored in plaintext. `set_token()` encrypts it with
    Fernet (key from env) and records only a one-way fingerprint + last-4 for display.
    `get_token()` decrypts server-side at call time (sync / test connection) and its result is
    never rendered or logged. All dangerous switches default OFF.
    """

    SYNC_MODE_DRY = "dry_run"
    SYNC_MODE_READ = "read_only"
    SYNC_MODE_APPLY = "apply_catalog"
    SYNC_MODES = [
        (SYNC_MODE_DRY, _("Dry run — read only, no DB writes")),
        (SYNC_MODE_READ, _("Read-only catalog — cache reads, no writes")),
        (SYNC_MODE_APPLY, _("Apply catalog (safe) — update local catalog only")),
    ]

    name = models.CharField(max_length=80, default="Primary")
    is_active = models.BooleanField(default=False, help_text=_("Use this account for sync / test connection."))
    shop_id = models.CharField(max_length=40, blank=True, default="")

    # --- secret: never exposed. All fields non-editable in forms/admin. ---
    token_ciphertext = models.TextField(blank=True, default="", editable=False)
    token_fingerprint = models.CharField(max_length=16, blank=True, default="", editable=False)
    token_last_four = models.CharField(max_length=4, blank=True, default="", editable=False)
    token_set_at = models.DateTimeField(null=True, blank=True, editable=False)
    token_updated_by = models.CharField(max_length=150, blank=True, default="", editable=False)

    # --- selected shop (chosen via 'Discover shops' -> 'Use this shop'; never typed) ---
    shop_title = models.CharField(max_length=120, blank=True, default="", editable=False)
    shop_sales_channel = models.CharField(max_length=60, blank=True, default="", editable=False)
    shop_selected_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- connection status (safe, no secret / no PII) ---
    last_connection_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_connection_status = models.CharField(max_length=20, blank=True, default="", editable=False)
    last_connection_error_safe = models.CharField(max_length=200, blank=True, default="", editable=False)
    last_connection_shop_name = models.CharField(max_length=120, blank=True, default="", editable=False)
    last_connection_product_count = models.PositiveIntegerField(null=True, blank=True, editable=False)

    # --- sync governance (safe defaults) ---
    sync_enabled = models.BooleanField(default=False)
    sync_interval_seconds = models.PositiveIntegerField(default=1800)
    sync_mode = models.CharField(max_length=20, choices=SYNC_MODES, default=SYNC_MODE_DRY)
    allow_product_publish = models.BooleanField(default=False, help_text=_("Superuser only. Keep OFF."))
    allow_order_creation = models.BooleanField(default=False, help_text=_("Superuser only. Keep OFF."))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Printify account")
        verbose_name_plural = _("Printify accounts")
        ordering = ["-is_active", "name"]

    def __str__(self):
        flag = "★ " if self.is_active else ""
        return f"{flag}{self.name}"

    # -- token handling (server-side only) -----------------------------------
    def has_token(self) -> bool:
        return bool(self.token_ciphertext)

    def set_token(self, plaintext, by=""):
        """Encrypt + store a new token. Raises secrets.SecretKeyMissing if no key is set."""
        from .secrets import encrypt_token, fingerprint
        plaintext = (plaintext or "").strip()
        if not plaintext:
            return
        self.token_ciphertext = encrypt_token(plaintext)
        self.token_fingerprint = fingerprint(plaintext)
        self.token_last_four = plaintext[-4:]
        self.token_set_at = timezone.now()
        self.token_updated_by = (by or "")[:150]

    def clear_token(self):
        self.token_ciphertext = ""
        self.token_fingerprint = ""
        self.token_last_four = ""
        self.token_set_at = None

    def get_token(self):
        """Decrypt the token for a Printify call. NEVER render or log the result."""
        from .secrets import decrypt_token
        return decrypt_token(self.token_ciphertext)

    def token_display(self):
        """Safe masked representation for the admin — never the real token."""
        if not self.token_last_four:
            return "—"
        return "•••• " + self.token_last_four

    def has_valid_shop(self) -> bool:
        """A shop is usable for sync only when a NUMERIC id has been selected."""
        return str(self.shop_id or "").isdigit()

    def set_shop(self, shop_id, title="", sales_channel=""):
        """Store the selected shop (numeric id + safe metadata). Used by 'Use this shop'."""
        self.shop_id = str(shop_id).strip()
        self.shop_title = (title or "")[:120]
        self.shop_sales_channel = (sales_channel or "")[:60]
        self.shop_selected_at = timezone.now()

    @classmethod
    def active(cls):
        """The active account, if any (used by the sync daemon / test connection)."""
        return cls.objects.filter(is_active=True).order_by("-updated_at").first()


class PrintifySyncState(models.Model):
    """Singleton (pk=1) coordinating the production-safe Printify sync daemon.

    Holds a DB-backed advisory lock (race-safe via a single conditional UPDATE,
    works on sqlite + Postgres and across separate systemd one-shot processes),
    a persisted exponential-backoff window after 429/5xx, the last-tick / last-full
    timestamps, and safe counters for monitoring. Stores NO token and NO PII.
    """
    SINGLETON_PK = 1

    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=120, blank=True, default="")
    last_tick_at = models.DateTimeField(null=True, blank=True)
    last_full_sync_at = models.DateTimeField(null=True, blank=True)
    backoff_until = models.DateTimeField(null=True, blank=True)
    backoff_level = models.IntegerField(default=0)
    consecutive_errors = models.IntegerField(default=0)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_status = models.IntegerField(null=True, blank=True)
    products_synced_total = models.BigIntegerField(default=0)
    last_tick_synced = models.IntegerField(default=0)
    last_tick_requests = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Printify Sync Monitor")
        verbose_name_plural = _("Printify Sync Monitor")

    def __str__(self):
        return f"PrintifySyncState(locked={bool(self.locked_at)}, backoff={bool(self.in_backoff())})"

    # -- singleton access -----------------------------------------------------
    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    # -- DB-backed lock (race-safe conditional UPDATE) ------------------------
    @classmethod
    def try_acquire(cls, owner, lock_timeout_seconds, now=None):
        """Atomically take the lock if free or its holder is stale. Returns True
        only for the single caller that wins the UPDATE."""
        now = now or timezone.now()
        cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        stale_before = now - timedelta(seconds=lock_timeout_seconds)
        won = cls.objects.filter(pk=cls.SINGLETON_PK).filter(
            Q(locked_at__isnull=True) | Q(locked_at__lt=stale_before)
        ).update(locked_at=now, locked_by=str(owner)[:120])
        return won == 1

    @classmethod
    def release(cls, owner=None):
        """Release the lock. With ``owner`` set, only release if we still hold it
        (so a tick whose stale lock was taken over does not clear the new holder's)."""
        qs = cls.objects.filter(pk=cls.SINGLETON_PK)
        if owner is not None:
            qs = qs.filter(locked_by=str(owner)[:120])
        qs.update(locked_at=None, locked_by="")

    # -- backoff --------------------------------------------------------------
    def in_backoff(self, now=None):
        now = now or timezone.now()
        return bool(self.backoff_until and self.backoff_until > now)

    def enter_backoff(self, base_seconds, status=None, now=None):
        now = now or timezone.now()
        self.backoff_level = min(self.backoff_level + 1, 8)
        wait = int(base_seconds) * (2 ** (self.backoff_level - 1))
        self.backoff_until = now + timedelta(seconds=wait)
        self.consecutive_errors += 1
        self.last_error_at = now
        if status is not None:
            self.last_error_status = int(status)
        return wait

    def clear_backoff(self):
        self.backoff_level = 0
        self.backoff_until = None
        self.consecutive_errors = 0


class SyncLog(models.Model):
    """Audit trail for Printify synchronisation runs (readable in the admin)."""

    KIND_PRODUCTS = "products"
    KIND_COSTS = "costs"
    KIND_ORDERS = "orders"
    KIND_SINGLE = "single_product"
    KIND_CHOICES = [
        (KIND_PRODUCTS, _("Products sync")),
        (KIND_COSTS, _("Variant costs sync")),
        (KIND_ORDERS, _("Order status pull")),
        (KIND_SINGLE, _("Single product resync")),
    ]

    STATUS_RUNNING = "running"
    STATUS_OK = "ok"
    STATUS_PARTIAL = "partial"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_RUNNING, _("Running")),
        (STATUS_OK, _("Success")),
        (STATUS_PARTIAL, _("Partial")),
        (STATUS_ERROR, _("Error")),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_PRODUCTS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    # richer, owner-facing counts so a report says exactly what happened + why
    skipped_count = models.PositiveIntegerField(default=0)
    hidden_count = models.PositiveIntegerField(default=0)
    missing_price_count = models.PositiveIntegerField(default=0)
    missing_image_count = models.PositiveIntegerField(default=0)
    shop_id = models.CharField(max_length=40, blank=True, default="")
    dry_run = models.BooleanField(default=False)
    detail = models.JSONField(default=dict, blank=True)  # to_review slugs + reasons + samples (safe)
    message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return round((self.finished_at - self.started_at).total_seconds(), 1)
        return None

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Printify sync log")
        verbose_name_plural = _("Printify sync logs")

    def __str__(self):
        return f"{self.get_kind_display()} • {self.get_status_display()} ({self.started_at:%Y-%m-%d %H:%M})"

    @property
    def duration(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class PrintifyShippingProfile(models.Model):
    """Persisted Printify shipping rate per (blueprint, provider, country).
    Admin/ops only — costs are supplier-side rates, never shown raw to customers."""
    blueprint_id = models.IntegerField(db_index=True)
    blueprint_title = models.CharField(max_length=160, blank=True, default="")
    print_provider_id = models.IntegerField(db_index=True)
    print_provider_name = models.CharField(max_length=120, blank=True, default="")
    country_code = models.CharField(max_length=4, db_index=True)
    first_item_cost = models.FloatField(default=0.0)
    additional_item_cost = models.FloatField(default=0.0)
    currency = models.CharField(max_length=8, default="EUR")
    handling_days = models.IntegerField(default=3)
    min_delivery_days = models.IntegerField(default=0)
    max_delivery_days = models.IntegerField(default=0)
    source = models.CharField(max_length=16, default="printify")
    last_checked_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blueprint_id", "print_provider_id", "country_code"],
                                    name="uniq_printify_shipping_profile"),
        ]
        ordering = ["blueprint_id", "country_code"]
        verbose_name = _("Printify shipping profile")
        verbose_name_plural = _("Printify shipping profiles")

    def __str__(self):
        return f"bp{self.blueprint_id}/pr{self.print_provider_id} → {self.country_code}"


class PrintifyShippingEstimateCache(models.Model):
    """Short-TTL cache of a pre-order shipping estimate (cost + computed delivery
    window) keyed by cart composition + coarse destination.

    Privacy: stores NO full address and NO PII — only an ISO country code and a
    postal-code PREFIX. `raw_response_safe` holds the per-method cost map (cents),
    never a token, customer name, email, phone, or street address.
    """
    SOURCE_LIVE = "live_printify"
    SOURCE_CACHED = "cached_profile"
    SOURCE_LOCAL = "local_fallback"
    SOURCE_UNAVAILABLE = "unavailable"

    cart_hash = models.CharField(max_length=64, db_index=True)
    country_code = models.CharField(max_length=4, db_index=True)
    postal_prefix = models.CharField(max_length=8, blank=True, default="")
    shipping_method = models.CharField(max_length=24, default="standard")
    source = models.CharField(max_length=16, default=SOURCE_LOCAL)
    currency = models.CharField(max_length=8, default="EUR")
    shipping_cost = models.FloatField(default=0.0)
    production_days_min = models.IntegerField(default=0)
    production_days_max = models.IntegerField(default=0)
    transit_days_min = models.IntegerField(default=0)
    transit_days_max = models.IntegerField(default=0)
    delivery_days_min = models.IntegerField(default=0)
    delivery_days_max = models.IntegerField(default=0)
    raw_response_safe = models.JSONField(default=dict, blank=True,
                                         help_text="Per-method cost map (cents). No PII, no token.")
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["cart_hash", "country_code", "postal_prefix", "shipping_method"],
                         name="idx_ship_estimate_lookup"),
        ]
        ordering = ["-created_at"]
        verbose_name = _("Printify shipping estimate (cached)")
        verbose_name_plural = _("Printify shipping estimates (cached)")

    def __str__(self):
        return f"{self.country_code}/{self.postal_prefix or '—'} {self.shipping_method} ({self.source})"

    @property
    def is_fresh(self) -> bool:
        from django.utils import timezone
        return bool(self.expires_at and self.expires_at > timezone.now())


class PrintifyPrintArea(models.Model):
    """Print area / placeholder coverage per product position (admin/data-quality only)."""
    product = models.ForeignKey("store.Product", on_delete=models.CASCADE,
                                related_name="print_areas")
    blueprint_id = models.IntegerField(null=True, blank=True)
    print_provider_id = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=40)
    placeholder_count = models.IntegerField(default=0)
    has_print_file = models.BooleanField(default=False)
    variant_count = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "position"],
                                    name="uniq_printify_print_area"),
        ]
        ordering = ["product", "position"]
        verbose_name = _("Printify print area")
        verbose_name_plural = _("Printify print areas")

    def __str__(self):
        return f"{self.product_id}:{self.position}"
