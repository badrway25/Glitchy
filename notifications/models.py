from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .events import EVENT_CHOICES


class OutboundEvent(models.Model):
    """A structured event dispatched from Django to n8n (email/automation)."""

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_RETRYING = "retrying"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_SENT, _("Sent")),
        (STATUS_FAILED, _("Failed")),
        (STATUS_RETRYING, _("Retrying")),
        (STATUS_SKIPPED, _("Skipped (n8n disabled)")),
    ]

    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    recipient_email = models.EmailField(blank=True, default="")
    language = models.CharField(max_length=5, default="en")
    payload = models.JSONField(default=dict, blank=True)

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    response_status = models.IntegerField(blank=True, null=True)
    last_error = models.TextField(blank=True, default="")

    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL,
                              blank=True, null=True, related_name="events")
    return_request = models.ForeignKey("returns.ReturnRequest", on_delete=models.SET_NULL,
                                       blank=True, null=True, related_name="events")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    dispatched_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Outbound event")
        verbose_name_plural = _("Outbound events (Django → n8n)")
        indexes = [
            models.Index(fields=["status", "event_type"]),
        ]

    def __str__(self):
        return f"{self.event_type} → {self.recipient_email or '-'} [{self.status}]"

    @property
    def can_retry(self):
        return self.status in {self.STATUS_FAILED, self.STATUS_RETRYING, self.STATUS_PENDING}

    def mark_sent(self, response_status=None):
        self.status = self.STATUS_SENT
        self.response_status = response_status
        self.last_error = ""
        self.dispatched_at = timezone.now()

    def mark_failed(self, error, response_status=None):
        self.attempts = (self.attempts or 0) + 1
        self.response_status = response_status
        self.last_error = str(error)[:2000]
        self.status = self.STATUS_FAILED if self.attempts >= self.max_attempts else self.STATUS_RETRYING


class SupportMessage(models.Model):
    """An inbound email/message synced from n8n into Django (support inbox)."""

    STATUS_NEW = "new"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, _("New")),
        (STATUS_IN_PROGRESS, _("In progress")),
        (STATUS_CLOSED, _("Closed")),
    ]

    from_email = models.EmailField(blank=True, default="")
    to_email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="")
    body_text = models.TextField(blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    language = models.CharField(max_length=5, blank=True, default="")

    message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    thread_id = models.CharField(max_length=255, blank=True, default="")
    attachments_meta = models.JSONField(default=list, blank=True)

    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL,
                              blank=True, null=True, related_name="support_messages")
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                blank=True, null=True, related_name="support_messages")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    is_auto_replied = models.BooleanField(default=False)

    received_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = _("Support message")
        verbose_name_plural = _("Support messages (inbound)")
        constraints = [
            models.UniqueConstraint(
                fields=["message_id"],
                condition=~models.Q(message_id=""),
                name="uniq_non_empty_message_id",
            ),
        ]

    def __str__(self):
        return f"{self.from_email}: {self.subject[:40]}"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    language = models.CharField(max_length=5, default="en")
    consent = models.BooleanField(default=True)
    source = models.CharField(max_length=64, blank=True, default="website")
    welcomed = models.BooleanField(default=False)
    unsubscribed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Newsletter subscriber")
        verbose_name_plural = _("Newsletter subscribers")

    def __str__(self):
        return self.email


class ContactRequest(models.Model):
    """A message sent from the public contact page.

    Stored first, dispatched second: if n8n or SMTP is down the customer's message
    is never lost — it sits here as `pending` and can be retried from the admin."""

    CATEGORY_ORDER = "order"
    CATEGORY_PAYMENT = "payment"
    CATEGORY_DELIVERY = "delivery"
    CATEGORY_RETURNS = "returns"
    CATEGORY_PRODUCT = "product"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_ORDER, _("Order question")),
        (CATEGORY_PAYMENT, _("Payment problem")),
        (CATEGORY_DELIVERY, _("Delivery and tracking")),
        (CATEGORY_RETURNS, _("Return or refund")),
        (CATEGORY_PRODUCT, _("Product information")),
        (CATEGORY_OTHER, _("Other")),
    ]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_SENT, _("Sent")),
        (STATUS_FAILED, _("Failed")),
        (STATUS_CLOSED, _("Closed")),
    ]

    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES,
                                default=CATEGORY_OTHER, db_index=True)
    order_number = models.CharField(max_length=40, blank=True, default="")
    message = models.TextField(max_length=4000)
    language = models.CharField(max_length=5, blank=True, default="en")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.SET_NULL,
                                blank=True, null=True, related_name='contact_requests')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL,
                              blank=True, null=True, related_name='contact_requests')
    event = models.ForeignKey('notifications.OutboundEvent', on_delete=models.SET_NULL,
                              blank=True, null=True, related_name='contact_requests')
    # sha256 of (email + message + category): lets us drop an accidental double-submit
    # without storing anything extra about the sender.
    fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    source = models.CharField(max_length=24, blank=True, default="contact_page")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "category"])]
        verbose_name = _("Contact request")
        verbose_name_plural = _("Contact requests")

    def __str__(self):
        return f"{self.email} · {self.get_category_display()}"
