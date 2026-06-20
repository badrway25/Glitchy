from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import SyncLog
from .services import pull_order_statuses, sync_products


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
