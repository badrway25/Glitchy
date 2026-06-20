import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from orders.models import Order, OrderProduct


class ReturnRequest(models.Model):
    STATUS_REQUESTED = "requested"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_REFUNDING = "refunding"
    STATUS_REFUNDED = "refunded"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_REQUESTED, _("Return requested")),
        (STATUS_APPROVED, _("Return approved")),
        (STATUS_REJECTED, _("Return rejected")),
        (STATUS_REFUNDING, _("Refund in progress")),
        (STATUS_REFUNDED, _("Refunded")),
        (STATUS_CLOSED, _("Closed")),
    ]

    # Statuses that customers/admin may still act on.
    OPEN_STATUSES = {STATUS_REQUESTED, STATUS_APPROVED, STATUS_REFUNDING}

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    customer_email = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    reason = models.TextField(blank=True, default="")
    admin_note = models.TextField(blank=True, default="")

    # Snapshot of eligibility at request time (window may have passed by review).
    within_window = models.BooleanField(default=True)
    refund_amount = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Return request")
        verbose_name_plural = _("Return requests")

    def __str__(self):
        return f"Return for {self.order.order_number} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def margin_after_refund(self):
        """Order net margin once this refund is applied."""
        from orders.margins import compute_margins_from_values

        return compute_margins_from_values(
            order_total=self.order.order_total,
            tax=self.order.tax,
            cost_production=self.order.cost_production,
            cost_shipping=self.order.cost_shipping,
            payment_fee=self.order.payment_fee,
            refunded_amount=max(self.order.refunded_amount, self.refund_amount),
            currency=self.order.currency,
        )

    def mark_processed(self):
        self.processed_at = timezone.now()


class ReturnItem(models.Model):
    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name="items")
    order_product = models.ForeignKey(OrderProduct, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return f"{self.quantity} × {self.order_product.product.product_name}"

    def refund_value(self):
        return float(self.order_product.product_price) * int(self.quantity)
