from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .dispatcher import resend_event
from .models import NewsletterSubscriber, OutboundEvent, SupportMessage


@admin.register(OutboundEvent)
class OutboundEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "recipient_email", "status_badge", "attempts",
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
    list_display = ("from_email", "subject", "status", "linked_order", "is_auto_replied",
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
    list_display = ("email", "language", "consent", "welcomed", "unsubscribed", "created_at")
    list_filter = ("language", "consent", "unsubscribed", "welcomed")
    search_fields = ("email",)
