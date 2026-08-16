from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from greatkart.admin_pii import masked_email_column
from .dispatcher import resend_event
from .models import (ContactRequest, NewsletterSubscriber, OutboundEvent,
                     SupportMessage)


@admin.register(OutboundEvent)
class OutboundEventAdmin(admin.ModelAdmin):
    masked_recipient = masked_email_column("recipient_email", _("Recipient"))
    list_display = ("event_type", "masked_recipient", "status_badge", "attempts",
                    "response_status", "created_at")
    list_filter = ("status", "event_type", "language")
    search_fields = ("recipient_email", "event_type", "order__order_number")
    readonly_fields = ("created_at", "updated_at", "dispatched_at", "payload",
                       "last_error", "response_status", "attempts")
    actions = ["resend_failed"]

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        colors = {"sent": "#16a34a", "pending": "#64748b", "failed": "#dc2626",
                  "retrying": "#d97706", "skipped": "#94a3b8"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span>',
            colors.get(obj.status, "#64748b"), obj.get_status_display())

    @admin.action(description=_("Resend selected events to n8n"))
    def resend_failed(self, request, queryset):
        sent = 0
        for event in queryset:
            resend_event(event)
            if event.status == OutboundEvent.STATUS_SENT:
                sent += 1
        self.message_user(request, _("Re-dispatched %(n)d event(s); %(s)d delivered.") % {
            "n": queryset.count(), "s": sent}, level=messages.INFO)


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    masked_from = masked_email_column("from_email", _("From"))
    list_display = ("masked_from", "subject", "status", "linked_order", "is_auto_replied",
                    "received_at")
    list_filter = ("status", "is_auto_replied", "language")
    search_fields = ("from_email", "subject", "body_text", "message_id")
    readonly_fields = ("message_id", "thread_id", "received_at", "created_at",
                       "attachments_meta", "body_html")
    list_editable = ("status",)

    @admin.display(description=_("Order"))
    def linked_order(self, obj):
        return obj.order.order_number if obj.order else "—"


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    masked_email = masked_email_column("email")
    list_display = ("masked_email", "language", "consent", "welcomed", "unsubscribed", "created_at")
    list_filter = ("language", "consent", "unsubscribed", "welcomed")
    search_fields = ("email",)


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    """Support queue for messages sent from the public contact page.

    Read-mostly: staff may move a request through its status and retry a failed
    dispatch, but never edit what the customer wrote. The list shows the masked
    email (data minimisation) — the full address stays on the detail page where
    it is needed to reply."""

    list_display = ("created_at", "masked_email", "name", "category_badge",
                    "order_number", "status_badge", "language")
    list_filter = ("status", "category", "created_at")
    search_fields = ("email", "name", "order_number", "message")
    readonly_fields = ("name", "email", "category", "order_number", "message",
                       "language", "account", "order", "event", "fingerprint",
                       "source", "created_at", "updated_at")
    fields = ("status",) + readonly_fields
    actions = ["mark_closed", "retry_dispatch"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("Email"))
    def masked_email(self, obj):
        from greatkart.pii import mask_email
        return mask_email(obj.email)

    @admin.display(description=_("Category"), ordering="category")
    def category_badge(self, obj):
        return obj.get_category_display()

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        colours = {"pending": "#d97706", "sent": "#16a34a",
                   "failed": "#dc2626", "closed": "#64748b"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>',
            colours.get(obj.status, "#94a3b8"), obj.get_status_display())

    @admin.action(description=_("Mark as closed"))
    def mark_closed(self, request, queryset):
        updated = queryset.update(status=ContactRequest.STATUS_CLOSED)
        self.message_user(request, _("%(n)d request(s) closed.") % {"n": updated})

    @admin.action(description=_("Retry sending"))
    def retry_dispatch(self, request, queryset):
        from .contact import _dispatch
        done = 0
        for contact in queryset.exclude(status=ContactRequest.STATUS_CLOSED):
            try:
                _dispatch(contact)
                done += 1
            except Exception:
                pass
        self.message_user(request, _("Retried %(n)d request(s).") % {"n": done})

# Mail Control Center (email/SMTP config) — registered in a dedicated module.
from . import admin_email  # noqa: E402,F401
