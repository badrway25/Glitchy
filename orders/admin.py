from django.conf import settings
from django.contrib import admin, messages
from django.db.models import F, FloatField, Sum
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Order, OrderProduct, Payment
from .services import push_order_to_printify

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


class OrderProductInline(admin.TabularInline):
    model = OrderProduct
    readonly_fields = ("payment", "user", "product", "quantity", "product_price",
                       "production_cost", "ordered")
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    change_list_template = "admin/orders/order_changelist.html"
    list_display = ("order_number", "email", "actor", "status", "is_ordered",
                    "total_display", "margin_display", "margin_pct_display",
                    "refunded_display", "printify_status", "created_at")
    list_filter = ("status", "is_ordered", "is_guest", MarginBandFilter, "created_at")
    search_fields = ("order_number", "first_name", "last_name", "email", "phone",
                     "printify_order_id")
    inlines = [OrderProductInline]
    actions = [accept_and_send, refresh_printify_status]
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

    @admin.display(description=_("Customer"))
    def actor(self, obj):
        return _("Guest") if obj.is_guest else (obj.user.email if obj.user else "—")

    @admin.display(description=_("Total"))
    def total_display(self, obj):
        return f"{obj.currency} {obj.order_total:.2f}"

    @admin.display(description=_("Net margin"))
    def margin_display(self, obj):
        m = obj.margins()
        colors = {"good": "#16a34a", "low": "#d97706", "negative": "#dc2626"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-weight:600;font-size:11px;">{} {:.2f}</span>',
            colors.get(m.band, "#64748b"), m.currency, m.net_margin)

    @admin.display(description=_("Margin %"))
    def margin_pct_display(self, obj):
        return f"{obj.margins().margin_pct:.1f}%"

    @admin.display(description=_("Refunded"))
    def refunded_display(self, obj):
        if not obj.refunded_amount:
            return "—"
        return format_html('<span style="color:#dc2626">-{} {:.2f}</span>',
                           obj.currency, obj.refunded_amount)

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
        html = "<table style='border-collapse:collapse'>"
        for label, val in rows:
            html += format_html(
                "<tr><td style='padding:2px 14px 2px 0;color:#555'>{}</td>"
                "<td style='text-align:right;font-variant-numeric:tabular-nums'>{} {:.2f}</td></tr>",
                label, m.currency, val)
        html += format_html(
            "<tr><td style='padding-top:4px;color:#555'>{}</td><td style='text-align:right'>{:.1f}%</td></tr>",
            _("Margin %"), m.margin_pct)
        html += "</table>"
        return format_html(html)

    def changelist_view(self, request, extra_context=None):
        qs = self.get_queryset(request).filter(is_ordered=True)
        agg = qs.aggregate(
            sales=Coalesce(Sum("order_total"), 0.0, output_field=FloatField()),
            production=Coalesce(Sum("cost_production"), 0.0, output_field=FloatField()),
            shipping=Coalesce(Sum("cost_shipping"), 0.0, output_field=FloatField()),
            fees=Coalesce(Sum("payment_fee"), 0.0, output_field=FloatField()),
            tax=Coalesce(Sum("tax"), 0.0, output_field=FloatField()),
            refunded=Coalesce(Sum("refunded_amount"), 0.0, output_field=FloatField()),
            net=Coalesce(Sum(NET_MARGIN_EXPR, output_field=FloatField()), 0.0),
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
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "user", "email", "payment_method", "amount_paid",
                    "status", "created_at")
    search_fields = ("payment_id", "email")
    list_filter = ("payment_method", "status")


admin.site.register(OrderProduct)
