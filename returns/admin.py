from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import ReturnItem, ReturnRequest


def _dispatch(return_request, event_name):
    try:
        from notifications.notify import notify_return_event
        from notifications import events as ev

        notify_return_event(return_request, getattr(ev, event_name))
    except Exception:
        pass


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ("order_product", "quantity", "reason")
    can_delete = False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order_number", "status_badge", "refund_display", "within_window",
                    "margin_after_refund_display", "created_at")
    list_filter = ("status", "within_window", "created_at")
    search_fields = ("order__order_number", "customer_email")
    readonly_fields = ("public_token", "created_at", "updated_at", "processed_at",
                       "margin_after_refund_display")
    inlines = [ReturnItemInline]
    actions = ["approve_returns", "reject_returns", "mark_refunding", "mark_refunded"]

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_number(self, obj):
        return obj.order.order_number

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            "requested": "#64748b", "approved": "#2563eb", "rejected": "#dc2626",
            "refunding": "#d97706", "refunded": "#16a34a", "closed": "#475569",
        }
        color = colors.get(obj.status, "#64748b")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 9px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span>', color, obj.get_status_display())

    @admin.display(description=_("Refund"))
    def refund_display(self, obj):
        return f"{obj.order.currency} {obj.refund_amount:.2f}"

    @admin.display(description=_("Net margin after refund"))
    def margin_after_refund_display(self, obj):
        m = obj.margin_after_refund()
        color = {"good": "#16a34a", "low": "#d97706", "negative": "#dc2626"}.get(m.band, "#475569")
        return format_html('<strong style="color:{}">{} {:.2f}</strong>',
                           color, m.currency, m.net_margin_after_refund)

    # --- State transitions ---
    @admin.action(description=_("Approve selected returns"))
    def approve_returns(self, request, queryset):
        for rr in queryset:
            rr.status = ReturnRequest.STATUS_APPROVED
            rr.save(update_fields=["status", "updated_at"])
            _dispatch(rr, "RETURN_APPROVED")
        self.message_user(request, _("Approved %(n)d return(s).") % {"n": queryset.count()})

    @admin.action(description=_("Reject selected returns"))
    def reject_returns(self, request, queryset):
        for rr in queryset:
            rr.status = ReturnRequest.STATUS_REJECTED
            rr.mark_processed()
            rr.save(update_fields=["status", "processed_at", "updated_at"])
            _dispatch(rr, "RETURN_REJECTED")
        self.message_user(request, _("Rejected %(n)d return(s).") % {"n": queryset.count()})

    @admin.action(description=_("Mark refund in progress"))
    def mark_refunding(self, request, queryset):
        queryset.update(status=ReturnRequest.STATUS_REFUNDING)

    @admin.action(description=_("Mark as refunded (updates order margin)"))
    def mark_refunded(self, request, queryset):
        count = queryset.count()
        for rr in queryset:
            order = rr.order
            # Apply the refund to the order's running refunded total.
            order.refunded_amount = float(order.refunded_amount or 0) + float(rr.refund_amount or 0)
            order.save(update_fields=["refunded_amount", "updated_at"])
            rr.status = ReturnRequest.STATUS_REFUNDED
            rr.mark_processed()
            rr.save(update_fields=["status", "processed_at", "updated_at"])
            _dispatch(rr, "REFUND_COMPLETED")
        self.message_user(request, _("Marked %(n)d return(s) as refunded.") % {"n": count},
                          level=messages.SUCCESS)
