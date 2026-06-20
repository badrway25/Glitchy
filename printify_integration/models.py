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
