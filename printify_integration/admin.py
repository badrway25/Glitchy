from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (PrintifyPrintArea, PrintifyShippingEstimateCache,
                     PrintifyShippingProfile, PrintifySyncState, SyncLog)
from .services import pull_order_statuses, sync_products
from .sync_daemon import status_snapshot


@admin.register(PrintifyShippingProfile)
class PrintifyShippingProfileAdmin(admin.ModelAdmin):
    list_display = ("country_code", "blueprint_id", "print_provider_name", "first_item_cost",
                    "additional_item_cost", "currency", "eta", "source", "last_checked_at")
    list_filter = ("source", "currency", "country_code")
    search_fields = ("country_code", "blueprint_id", "print_provider_name")

    @admin.display(description=_("ETA"))
    def eta(self, obj):
        return f"{obj.min_delivery_days}-{obj.max_delivery_days}d"


@admin.register(PrintifyPrintArea)
class PrintifyPrintAreaAdmin(admin.ModelAdmin):
    list_display = ("product", "position", "placeholder_count", "has_print_file",
                    "variant_count", "last_synced_at")
    list_filter = ("position", "has_print_file")
    search_fields = ("product__product_name",)


@admin.register(PrintifyShippingEstimateCache)
class PrintifyShippingEstimateCacheAdmin(admin.ModelAdmin):
    """Ops view of recent pre-order estimates. Read-only; rows expire on their TTL.
    Contains no PII — only a country code, postal PREFIX and per-method costs."""
    list_display = ("country_code", "postal_prefix", "shipping_method", "source_badge",
                    "shipping_cost", "currency", "delivery", "fresh", "created_at")
    list_filter = ("source", "currency", "country_code", "shipping_method")
    search_fields = ("country_code", "postal_prefix")
    readonly_fields = [f.name for f in PrintifyShippingEstimateCache._meta.fields]
    actions = ["purge_expired"]

    @admin.display(description=_("Source"))
    def source_badge(self, obj):
        colors = {"live_printify": "#16a34a", "cached_profile": "#0ea5e9",
                  "local_fallback": "#d97706", "unavailable": "#64748b"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span>',
            colors.get(obj.source, "#64748b"), obj.source)

    @admin.display(description=_("Delivery"))
    def delivery(self, obj):
        return f"{obj.delivery_days_min}-{obj.delivery_days_max}d"

    @admin.display(boolean=True, description=_("Fresh"))
    def fresh(self, obj):
        return obj.is_fresh

    @admin.action(description=_("Purge expired estimate cache rows"))
    def purge_expired(self, request, queryset):
        from django.utils import timezone
        n, _x = PrintifyShippingEstimateCache.objects.filter(
            expires_at__lte=timezone.now()).delete()
        self.message_user(request, _("Purged %(n)d expired estimate row(s).") % {"n": n})


@admin.register(PrintifySyncState)
class PrintifySyncStateAdmin(admin.ModelAdmin):
    """Read-only monitor for the production-safe sync daemon (no token, no PII)."""
    list_display = ("monitor", "last_tick_at", "backoff_until", "consecutive_errors",
                    "products_synced_total", "updated_at")
    readonly_fields = [f.name for f in PrintifySyncState._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Sync daemon"))
    def monitor(self, obj):
        snap = status_snapshot()
        on = snap["enabled"]
        color = "#16a34a" if on else "#64748b"
        label = "ENABLED" if on else "disabled"
        extra = " · BACKOFF" if snap["backoff_active"] else ""
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span> &nbsp;stale: {}{}',
            color, label, snap["stale_products"], extra)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("kind", "status_badge", "created_count", "updated_count",
                    "error_count", "duration_display", "started_at")
    list_filter = ("kind", "status")
    readonly_fields = [f.name for f in SyncLog._meta.fields]
    actions = ["run_product_sync", "run_order_pull"]

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        colors = {"ok": "#16a34a", "partial": "#d97706", "error": "#dc2626", "running": "#64748b"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span>',
            colors.get(obj.status, "#64748b"), obj.get_status_display())

    @admin.display(description=_("Duration"))
    def duration_display(self, obj):
        d = obj.duration
        return f"{d:.1f}s" if d is not None else "—"

    @admin.action(description=_("Run a full Printify product sync now"))
    def run_product_sync(self, request, queryset):
        log = sync_products()
        self.message_user(request, _("Product sync finished: +%(c)d ~%(u)d (errors %(e)d).") % {
            "c": log.created_count, "u": log.updated_count, "e": log.error_count})

    @admin.action(description=_("Pull Printify order statuses now"))
    def run_order_pull(self, request, queryset):
        log = pull_order_statuses()
        self.message_user(request, _("Order pull finished: %(u)d updated (errors %(e)d).") % {
            "u": log.updated_count, "e": log.error_count})
