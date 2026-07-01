from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from . import secrets as printify_secrets
from .models import (PrintifyAccountConfig, PrintifyPrintArea,
                     PrintifyShippingEstimateCache, PrintifyShippingProfile,
                     PrintifySyncState, SyncLog)
from .services import pull_order_statuses, sync_products
from .sync_daemon import status_snapshot


def _is_superadmin(user):
    """The project's custom Account uses is_superadmin (not Django's is_superuser)."""
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_superuser", False))


class PrintifyAccountConfigForm(forms.ModelForm):
    # Write-only token entry. render_value=False guarantees the stored value is NEVER sent to
    # the browser. The real token lives only as ciphertext on the model (never a form field).
    new_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        label=_("Set / replace API token"),
        help_text=_("Write-only. Leave blank to keep the current token. The token is encrypted "
                    "at rest and can never be viewed again after saving."),
    )

    class Meta:
        model = PrintifyAccountConfig
        fields = ("name", "is_active", "shop_id", "new_token", "sync_enabled",
                  "sync_interval_seconds", "sync_mode", "allow_product_publish",
                  "allow_order_creation")

    def clean_new_token(self):
        token = (self.cleaned_data.get("new_token") or "").strip()
        if token and not printify_secrets.has_key():
            raise forms.ValidationError(
                _("PRINTIFY_CONFIG_KEY is not configured on the server, so the token cannot be "
                  "encrypted. Set that environment key first (a Fernet key)."))
        return token


def _token_badge(present):
    color = "#16a34a" if present else "#64748b"
    label = _("set") if present else _("none")
    return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
                       'font-size:11px;font-weight:600;">{}</span>', color, label)


@admin.register(PrintifyAccountConfig)
class PrintifyAccountConfigAdmin(admin.ModelAdmin):
    """Secure admin for Printify credentials. The token is write-only, encrypted at rest, and
    NEVER rendered in the form, list, detail or history — only a masked last-4 + fingerprint."""
    form = PrintifyAccountConfigForm
    list_display = ("name", "is_active", "shop_id", "token_state", "sync_enabled",
                    "sync_mode", "connection_state", "updated_at")
    list_filter = ("is_active", "sync_enabled", "sync_mode")
    search_fields = ("name", "shop_id")
    actions = ["action_test_connection", "action_sync_dry_run", "action_sync_apply_safe"]
    readonly_fields = ("token_state_detail", "connection_state_detail", "token_set_at",
                       "token_updated_by", "created_at", "updated_at")
    fieldsets = (
        (_("Account"), {"fields": ("name", "is_active", "shop_id")}),
        (_("API token (write-only)"), {"fields": ("new_token", "token_state_detail",
                                                  "token_set_at", "token_updated_by")}),
        (_("Sync governance"), {"fields": ("sync_enabled", "sync_interval_seconds", "sync_mode",
                                           "allow_product_publish", "allow_order_creation")}),
        (_("Connection status (read-only)"), {"fields": ("connection_state_detail",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )

    # -- permissions: only superusers touch the token + dangerous switches ----
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not _is_superadmin(request.user):
            ro += ["sync_mode", "allow_product_publish", "allow_order_creation"]
        return ro

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _is_superadmin(request.user) and "new_token" in form.base_fields:
            # non-superusers cannot enter a token at all
            form.base_fields.pop("new_token", None)
        return form

    def save_model(self, request, obj, form, change):
        token = form.cleaned_data.get("new_token") if _is_superadmin(request.user) else ""
        if token:
            by = getattr(request.user, "email", "") or request.user.get_username()
            obj.set_token(token, by=by)   # encrypts; plaintext is discarded here
        super().save_model(request, obj, form, change)

    # -- safe display --------------------------------------------------------
    @admin.display(description=_("Token"))
    def token_state(self, obj):
        return format_html("{} {}", _token_badge(obj.has_token()),
                           obj.token_display() if obj.has_token() else "")

    @admin.display(description=_("Token status"))
    def token_state_detail(self, obj):
        if not obj.has_token():
            return format_html("{} — {}", _token_badge(False), _("no token stored"))
        return format_html("{} &nbsp; {} &nbsp; <code>fp:{}</code>",
                           _token_badge(True), obj.token_display(), obj.token_fingerprint)

    @admin.display(description=_("Connection"))
    def connection_state(self, obj):
        s = obj.last_connection_status or "unknown"
        color = {"connected": "#16a34a", "failed": "#dc2626"}.get(s, "#64748b")
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;'
                           'border-radius:999px;font-size:11px;font-weight:600;">{}</span>', color, s)

    @admin.display(description=_("Connection status"))
    def connection_state_detail(self, obj):
        if not obj.last_connection_check_at:
            return _("Never tested. Use the 'Test connection' action.")
        parts = [self.connection_state(obj)]
        if obj.last_connection_shop_name:
            parts.append(format_html(" &nbsp; shop: <strong>{}</strong>", obj.last_connection_shop_name))
        if obj.last_connection_product_count is not None:
            parts.append(format_html(" &nbsp; products: {}", obj.last_connection_product_count))
        if obj.last_connection_error_safe:
            parts.append(format_html(" &nbsp; <span style='color:#dc2626'>{}</span>", obj.last_connection_error_safe))
        parts.append(format_html(" &nbsp; <em>{}</em>", obj.last_connection_check_at.strftime("%Y-%m-%d %H:%M")))
        from django.utils.safestring import mark_safe
        return mark_safe("".join(str(p) for p in parts))   # parts are already-escaped SafeStrings

    # -- actions (read-only Printify; never print the token) ------------------
    @admin.action(description=_("Test connection (read-only)"))
    def action_test_connection(self, request, queryset):
        for cfg in queryset:
            self._test_one(request, cfg)

    def _test_one(self, request, cfg):
        from .printify_client import PrintifyClient, PrintifyError
        token = cfg.get_token() or ""
        cfg.last_connection_check_at = timezone.now()
        if not token:
            cfg.last_connection_status = "failed"
            cfg.last_connection_error_safe = "No token set"
            cfg.save(update_fields=["last_connection_check_at", "last_connection_status", "last_connection_error_safe"])
            self.message_user(request, _("%(n)s: no token set.") % {"n": cfg.name}, level="warning")
            return
        try:
            client = PrintifyClient(token=token, shop_id=cfg.shop_id)
            shops = client.get_shops() or []
            shop = next((s for s in shops if str(s.get("id")) == str(cfg.shop_id)), (shops[0] if shops else {}))
            pc = None
            try:
                prods = client.list_products(shop_id=cfg.shop_id or (shop.get("id") if shop else None), limit=1)
                pc = prods.get("total") if isinstance(prods, dict) else None
            except Exception:
                pc = None
            cfg.last_connection_status = "connected"
            cfg.last_connection_error_safe = ""
            cfg.last_connection_shop_name = str(shop.get("title", ""))[:120] if shop else ""
            cfg.last_connection_product_count = pc
            cfg.save(update_fields=["last_connection_check_at", "last_connection_status",
                                    "last_connection_error_safe", "last_connection_shop_name",
                                    "last_connection_product_count"])
            self.message_user(request, _("%(n)s: connected.") % {"n": cfg.name})
        except PrintifyError as e:
            cfg.last_connection_status = "failed"
            cfg.last_connection_error_safe = ("HTTP %s" % getattr(e, "status", "")).strip()[:200] or "Connection error"
            cfg.save(update_fields=["last_connection_check_at", "last_connection_status", "last_connection_error_safe"])
            self.message_user(request, _("%(n)s: connection failed.") % {"n": cfg.name}, level="error")
        except Exception:
            cfg.last_connection_status = "failed"
            cfg.last_connection_error_safe = "Connection error"
            cfg.save(update_fields=["last_connection_check_at", "last_connection_status", "last_connection_error_safe"])
            self.message_user(request, _("%(n)s: connection failed.") % {"n": cfg.name}, level="error")

    @admin.action(description=_("Sync now — DRY RUN (no writes)"))
    def action_sync_dry_run(self, request, queryset):
        from .sync_daemon import run_tick
        res = run_tick(apply=False, force=True)          # apply=False => never writes
        msg = (res.messages[0] if getattr(res, "messages", None) else res.reason)
        self.message_user(request, _("Dry-run sync: %(s)s") % {"s": msg})

    @admin.action(description=_("Sync now — apply safe catalog (superuser)"))
    def action_sync_apply_safe(self, request, queryset):
        if not _is_superadmin(request.user):
            self.message_user(request, _("Only a superuser can apply a catalog sync."), level="error")
            return
        log = sync_products()
        self.message_user(request, _("Catalog sync: +%(c)d ~%(u)d (errors %(e)d).") % {
            "c": log.created_count, "u": log.updated_count, "e": log.error_count})


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
