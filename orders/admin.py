from django.conf import settings
from django.contrib import admin, messages
from django.db.models import F, FloatField, Sum
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
    from unfold.admin import TabularInline as BaseTabularInline
except Exception:
    from django.contrib.admin import ModelAdmin as BaseModelAdmin
    from django.contrib.admin import TabularInline as BaseTabularInline

from .models import Order, OrderProduct, Payment
from .services import push_order_to_printify


def _pill(text, color, *, solid=False):
    """A refined status/label pill — soft tinted by default, matching the premium palette."""
    if solid:
        style = ("background:%s;color:#fff;" % color)
    else:
        style = ("background:%s1f;color:%s;box-shadow:inset 0 0 0 1px %s3d;" % (color, color, color))
    return format_html('<span style="{}padding:2px 10px;border-radius:999px;font-size:11px;'
                       'font-weight:600;white-space:nowrap;">{}</span>', mark_safe(style), text)

# Net-margin expression reused for annotation/filtering/aggregation.
NET_MARGIN_EXPR = (
    Coalesce(F("order_total"), 0.0)
    - Coalesce(F("tax"), 0.0)
    - Coalesce(F("cost_production"), 0.0)
    - Coalesce(F("cost_shipping"), 0.0)
    - Coalesce(F("payment_fee"), 0.0)
    - Coalesce(F("refunded_amount"), 0.0)
)


@admin.action(description=_("Accept order and send to Printify"))
def accept_and_send(modeladmin, request, queryset):
    for order in queryset:
        order.status = "Accepted"
        order.save(update_fields=["status"])
        try:
            push_order_to_printify(order, auto_send=True)
            messages.success(request, f"Sent {order.order_number} to Printify.")
        except Exception as exc:
            messages.error(request, f"Printify error for {order.order_number}: {exc}")


@admin.action(description=_("Refresh Printify status/tracking"))
def refresh_printify_status(modeladmin, request, queryset):
    from printify_integration.services import pull_order_statuses

    pull_order_statuses(limit=queryset.count() or 20)
    messages.info(request, _("Refreshed Printify statuses."))


def _fire(request, queryset, event_name, label, require_tracking=False):
    """Operator-driven fulfillment email (works even without Printify connected)."""
    from notifications.notify import notify_order_event
    from notifications import events as ev
    sent = skipped = 0
    for order in queryset:
        if require_tracking and not order.tracking_number:
            skipped += 1
            continue
        try:
            notify_order_event(order, getattr(ev, event_name))
            sent += 1
        except Exception:
            skipped += 1
    messages.info(request, _("%(label)s: sent %(s)d, skipped %(k)d.") % {"label": label, "s": sent, "k": skipped})


@admin.action(description=_("Email: order in production"))
def email_in_production(modeladmin, request, queryset):
    for o in queryset:
        if o.status != "In production":
            o.status = "In production"; o.save(update_fields=["status"])
    _fire(request, queryset, "ORDER_IN_PRODUCTION", _("In-production email"))


@admin.action(description=_("Email: order shipped"))
def email_shipped(modeladmin, request, queryset):
    _fire(request, queryset, "ORDER_SHIPPED", _("Shipped email"))


@admin.action(description=_("Email: tracking available (needs tracking number)"))
def email_tracking(modeladmin, request, queryset):
    _fire(request, queryset, "ORDER_TRACKING", _("Tracking email"), require_tracking=True)


class MarginBandFilter(admin.SimpleListFilter):
    title = _("margin")
    parameter_name = "margin_band"

    def lookups(self, request, model_admin):
        return [("positive", _("Positive")), ("negative", _("Negative / loss"))]

    def queryset(self, request, queryset):
        if self.value() == "positive":
            return queryset.annotate(_net=NET_MARGIN_EXPR).filter(_net__gte=0)
        if self.value() == "negative":
            return queryset.annotate(_net=NET_MARGIN_EXPR).filter(_net__lt=0)
        return queryset


class OrderProductInline(BaseTabularInline):
    model = OrderProduct
    readonly_fields = ("line_thumb", "payment", "user", "product", "quantity",
                       "product_price", "production_cost", "ordered")
    fields = readonly_fields
    extra = 0

    @admin.display(description=_("Image"))
    def line_thumb(self, obj):
        url = obj.line_image_url() if obj and obj.pk else ""
        if not url:
            return "—"
        return format_html('<img src="{}" style="width:44px;height:44px;object-fit:cover;'
                           'border-radius:8px;" loading="lazy">', url)


@admin.register(Order)
class OrderAdmin(BaseModelAdmin):
    change_list_template = "admin/orders/order_changelist.html"

    # Orders are created by the checkout flow, never hand-added in the admin. Disabling add
    # also removes the broken /add/ page (created_at is a non-editable field in the fieldsets).
    def has_add_permission(self, request):
        return False

    list_display = ("order_number", "actor", "status_badge", "is_ordered",
                    "total_display", "margin_display", "margin_pct_display",
                    "refunded_display", "printify_badge", "created_at")
    list_filter = ("status", "is_ordered", "is_guest", MarginBandFilter, "created_at")
    search_fields = ("order_number", "first_name", "last_name", "email", "phone",
                     "printify_order_id")
    inlines = [OrderProductInline]
    actions = [accept_and_send, refresh_printify_status,
               email_in_production, email_shipped, email_tracking]
    readonly_fields = ("margin_breakdown",)
    fieldsets = (
        (None, {"fields": ("order_number", "user", "is_guest", "status", "is_ordered",
                           "payment", "created_at")}),
        (_("Customer"), {"fields": ("first_name", "last_name", "email", "phone")}),
        (_("Shipping address"), {"fields": ("address_line_1", "address_line_2", "city",
                                            "state", "postal_code", "country",
                                            "shipping_country", "shipping_min_days",
                                            "shipping_max_days")}),
        (_("Money & margin"), {"fields": ("currency", "items_subtotal", "shipping_cost",
                                          "tax", "order_total", "cost_production",
                                          "cost_shipping", "payment_fee", "refunded_amount",
                                          "margin_breakdown")}),
        (_("Printify fulfilment"), {"fields": ("printify_order_id", "printify_status",
                                               "printify_last_error", "tracking_number",
                                               "tracking_url", "carrier")}),
    )

    @admin.display(description=_("Email"))
    def masked_email(self, obj):
        from greatkart.pii import mask_email
        return mask_email(obj.email)

    @admin.display(description=_("Customer"))
    def actor(self, obj):
        from greatkart.pii import mask_email, mask_name
        if obj.is_guest:
            return _("Guest")
        if obj.user:
            return mask_email(obj.user.email)
        return mask_name(obj.first_name, obj.last_name) or "—"

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        colors = {"New": "#64748b", "Accepted": "#2563eb", "In production": "#a6824c",
                  "Completed": "#16a34a", "Cancelled": "#dc2626"}
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return _pill(label, colors.get(obj.status, "#64748b"))

    @admin.display(description=_("Printify"))
    def printify_badge(self, obj):
        s = obj.printify_status or "—"
        if s in ("—", "", None):
            return "—"
        colors = {"error": "#dc2626", "fulfilled": "#16a34a", "in_production": "#a6824c",
                  "on-hold": "#d97706"}
        return _pill(s, colors.get(s, "#64748b"))

    @admin.display(description=_("Total"))
    def total_display(self, obj):
        return format_html('<span style="font-variant-numeric:tabular-nums;">{}</span>',
                           f"{obj.currency} {obj.order_total:.2f}")

    @admin.display(description=_("Net margin"))
    def margin_display(self, obj):
        m = obj.margins()
        colors = {"good": "#16a34a", "low": "#d97706", "negative": "#dc2626"}
        return _pill(f"{m.currency} {m.net_margin:.2f}", colors.get(m.band, "#64748b"))

    @admin.display(description=_("Margin %"))
    def margin_pct_display(self, obj):
        return f"{obj.margins().margin_pct:.1f}%"

    @admin.display(description=_("Refunded"))
    def refunded_display(self, obj):
        if not obj.refunded_amount:
            return "—"
        return format_html('<span style="color:#dc2626">{}</span>',
                           f"-{obj.currency} {obj.refunded_amount:.2f}")

    @admin.display(description=_("Margin breakdown"))
    def margin_breakdown(self, obj):
        m = obj.margins()
        rows = [
            (_("Revenue (excl. tax)"), m.revenue_ex_tax),
            (_("Production cost"), -m.cost_production),
            (_("Shipping cost"), -m.cost_shipping),
            (_("Payment fee"), -m.payment_fee),
            (_("Refunded"), -m.refunded_amount),
            (_("Net margin"), m.net_margin),
        ]
        parts = ["<table style='border-collapse:collapse'>"]
        for label, val in rows:
            parts.append(format_html(
                "<tr><td style='padding:2px 14px 2px 0;color:#555'>{}</td>"
                "<td style='text-align:right;font-variant-numeric:tabular-nums'>{}</td></tr>",
                label, f"{m.currency} {val:.2f}"))
        parts.append(format_html(
            "<tr><td style='padding-top:4px;color:#555'>{}</td><td style='text-align:right'>{}</td></tr>",
            _("Margin %"), f"{m.margin_pct:.1f}%"))
        parts.append("</table>")
        return mark_safe("".join(str(p) for p in parts))

    def changelist_view(self, request, extra_context=None):
        qs = self.get_queryset(request).filter(is_ordered=True)
        agg = qs.aggregate(
            sales=Coalesce(Sum("order_total"), 0.0, output_field=FloatField()),
            production=Coalesce(Sum("cost_production"), 0.0, output_field=FloatField()),
            shipping=Coalesce(Sum("cost_shipping"), 0.0, output_field=FloatField()),
            net=Coalesce(Sum(NET_MARGIN_EXPR, output_field=FloatField()), 0.0,
                         output_field=FloatField()),
        )
        kpis = {
            "sales": round(agg["sales"], 2),
            "printify_costs": round(agg["production"] + agg["shipping"], 2),
            "net_margin": round(agg["net"], 2),
            "refunded_orders": qs.filter(refunded_amount__gt=0).count(),
            "error_orders": qs.filter(printify_status="error").count(),
            "to_complete": qs.filter(status__in=["New", "Accepted"]).count(),
            "currency": getattr(settings, "STORE_CURRENCY", "EUR"),
        }
        extra_context = extra_context or {}
        extra_context["kpis"] = kpis
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Payment)
class PaymentAdmin(BaseModelAdmin):
    list_display = ("payment_id", "user", "email", "payment_method", "amount_paid",
                    "status", "created_at")
    search_fields = ("payment_id", "email")
    list_filter = ("payment_method", "status")


admin.site.register(OrderProduct)
