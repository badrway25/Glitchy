from django.db import models
from django.utils.translation import gettext_lazy as _


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
    message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

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
