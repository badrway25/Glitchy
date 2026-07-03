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
        # shop_id is intentionally NOT here — it is chosen via "Discover shops" -> "Use this
        # shop" (numeric id only), never typed by hand.
        fields = ("name", "is_active", "new_token", "sync_enabled",
                  "sync_interval_seconds", "sync_mode", "allow_product_publish",
                  "allow_order_creation")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A custom ModelForm's fields get Django's bare vTextField widgets, which Unfold does
        # NOT style -> the inputs render ~invisible. Give each widget Unfold's own input class
        # so they look native to the premium admin. (Import lazily: unfold.widgets touches
        # settings at import time.)
        from unfold.widgets import (INPUT_CLASSES, SELECT_CLASSES, CHECKBOX_CLASSES)
        text = " ".join(INPUT_CLASSES)
        select = " ".join(SELECT_CLASSES)
        checkbox = " ".join(CHECKBOX_CLASSES)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (w.attrs.get("class", "") + " " + checkbox).strip()
            elif isinstance(w, forms.Select):
                w.attrs["class"] = (w.attrs.get("class", "") + " " + select).strip()
            elif isinstance(w, (forms.TextInput, forms.NumberInput, forms.PasswordInput,
                                forms.EmailInput, forms.URLInput, forms.Textarea)):
                w.attrs["class"] = (w.attrs.get("class", "") + " " + text).strip()

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
    change_form_template = "admin/printify_integration/printifyaccountconfig/change_form.html"
    readonly_fields = ("token_state_detail", "connection_state_detail", "printify_ops_panel",
                       "token_set_at", "token_updated_by", "created_at", "updated_at")
    # Full layout (editing an existing account) — includes the operations panel + status blocks.
    fieldsets = (
        (_("Account"), {"fields": ("name", "is_active")}),
        (_("API token (write-only)"), {"fields": ("new_token", "token_state_detail",
                                                  "token_set_at", "token_updated_by")}),
        (_("Printify shop & operations"), {"fields": ("printify_ops_panel",)}),
        (_("Sync governance"), {"fields": ("sync_enabled", "sync_interval_seconds", "sync_mode",
                                           "allow_product_publish", "allow_order_creation")}),
        (_("Connection status (read-only)"), {"fields": ("connection_state_detail",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )
    # Slim layout when CREATING — no shop_id (chosen after save via Discover shops), no
    # auto/read-only fields (empty on add).
    add_fieldsets = (
        (_("Account"), {"fields": ("name", "is_active"),
                        "description": _("Enter a name and API token, then Save. After saving, "
                                         "use 'Discover shops' to select your Printify shop.")}),
        (_("API token (write-only)"), {"fields": ("new_token",)}),
        (_("Sync governance"), {"fields": ("sync_enabled", "sync_interval_seconds", "sync_mode",
                                           "allow_product_publish", "allow_order_creation")}),
    )

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.fieldsets

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

    # -- Printify operations: status panel (buttons live in the change_form template) --------
    @admin.display(description=_("Printify shop & operations"))
    def printify_ops_panel(self, obj):
        from django.utils.safestring import mark_safe
        if obj is None or not obj.pk:
            return _("Save the account first, then use 'Discover shops'.")
        rows = []
        if obj.has_valid_shop():
            rows.append("<div style='font-weight:700;margin-bottom:.2rem;'>%s</div>" % _("Selected shop"))
            rows.append("<div>ID: <code>%s</code></div>" % obj.shop_id)
            if obj.shop_title:
                rows.append("<div>%s: <strong>%s</strong></div>" % (_("Title"), obj.shop_title))
            if obj.shop_sales_channel:
                rows.append("<div>%s: %s</div>" % (_("Sales channel"), obj.shop_sales_channel))
        elif obj.shop_id:
            rows.append("<div style='color:#b3554e;font-weight:600;'>%s</div>" % (
                _("“%s” looks like a shop name, not a numeric Printify shop ID. "
                  "Use Discover shops to select the correct shop.") % obj.shop_id))
        else:
            rows.append("<div style='color:#8a8177;'>%s</div>" % _("No shop selected yet."))
        last = SyncLog.objects.filter(kind=SyncLog.KIND_PRODUCTS).order_by("-started_at").first()
        if last:
            pill = ("display:inline-block;padding:.1rem .5rem;border-radius:999px;"
                    "border:1px solid var(--gl-line,#e7e0d4);margin:.15rem .3rem .15rem 0;font-size:.8em;")
            rows.append("<div style='margin-top:.7rem;font-weight:600;'>%s%s</div>" % (
                _("Latest sync report"), (" · DRY-RUN" if last.dry_run else "")))
            rows.append(
                "<div style='margin-top:.3rem;'>"
                "<span style='%s'>%s created</span><span style='%s'>%s updated</span>"
                "<span style='%s'>%s hidden</span><span style='%s'>%s skipped</span>"
                "<span style='%s'>%s errors</span></div>" % (
                    pill, last.created_count, pill, last.updated_count, pill, last.hidden_count,
                    pill, last.skipped_count, pill, last.error_count))
            if last.missing_price_count or last.missing_image_count:
                rows.append("<div style='opacity:.75;font-size:.82em;margin-top:.2rem;'>%s</div>" % (
                    _("Needs review — missing price: %(p)d, missing image: %(i)d")
                    % {"p": last.missing_price_count, "i": last.missing_image_count}))
            # next-action links: hidden products + full sync log
            rows.append(
                "<div style='margin-top:.45rem;font-size:.85em;'>"
                "<a href='/admin/store/product/?is_available__exact=0' style='color:var(--gl-gold,#a6824c);'>%s</a>"
                " &nbsp;·&nbsp; <a href='/admin/store/product/' style='color:var(--gl-gold,#a6824c);'>%s</a>"
                " &nbsp;·&nbsp; <a href='/admin/printify_integration/synclog/%s/change/' style='color:var(--gl-gold,#a6824c);'>%s</a></div>"
                % (_("View hidden products"), _("All products"), last.pk, _("Full report")))
        rows.append("<div style='margin-top:.5rem;opacity:.7;font-size:.82em;'>%s</div>"
                    % _("Publishing and order creation stay OFF; sync updates the local catalogue only."))
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(rows))

    # -- custom admin URLs (all state-changing ops are POST + superadmin-gated) --------------
    def get_urls(self):
        from django.urls import path
        base = "printify_integration_printifyaccountconfig"
        custom = [
            path("<int:pk>/discover-shops/", self.admin_site.admin_view(self._discover_view),
                 name="%s_discover" % base),
            path("<int:pk>/use-shop/<str:shop_id>/", self.admin_site.admin_view(self._use_shop_view),
                 name="%s_use_shop" % base),
            path("<int:pk>/test-connection/", self.admin_site.admin_view(self._test_view),
                 name="%s_test" % base),
            path("<int:pk>/sync-now/", self.admin_site.admin_view(self._sync_view),
                 name="%s_sync" % base),
            path("<int:pk>/dry-run/", self.admin_site.admin_view(self._dryrun_view),
                 name="%s_dryrun" % base),
        ]
        return custom + super().get_urls()

    def _guard(self, request, pk):
        from django.http import HttpResponseForbidden
        if request.method != "POST":
            return None, self._redirect(pk)
        if not _is_superadmin(request.user):
            return None, HttpResponseForbidden("Superuser only.")
        cfg = PrintifyAccountConfig.objects.filter(pk=pk).first()
        if not cfg:
            return None, self._redirect(pk)
        return cfg, None

    def _redirect(self, pk):
        from django.shortcuts import redirect
        return redirect("admin:printify_integration_printifyaccountconfig_change", pk)

    def _discover_view(self, request, pk):
        cfg, err = self._guard(request, pk)
        if err:
            return err
        from .services import discover_shops
        res = discover_shops(cfg)
        if res["ok"]:
            request.session["printify_shops_%s" % pk] = res["shops"]
            self.message_user(request, _("Found %(n)d shop(s). Pick one below with 'Use this shop'.")
                              % {"n": len(res["shops"])})
        else:
            self.message_user(request, _("Discover shops failed: %(e)s") % {"e": res["error"]}, level="error")
        return self._redirect(pk)

    def _use_shop_view(self, request, pk, shop_id):
        cfg, err = self._guard(request, pk)
        if err:
            return err
        if not str(shop_id).isdigit():
            self.message_user(request, _("Invalid shop ID (must be numeric)."), level="error")
            return self._redirect(pk)
        shops = request.session.get("printify_shops_%s" % pk, [])
        shop = next((s for s in shops if str(s.get("id")) == str(shop_id)), {})
        cfg.set_shop(shop_id, shop.get("title", ""), shop.get("sales_channel", ""))
        cfg.save(update_fields=["shop_id", "shop_title", "shop_sales_channel", "shop_selected_at"])
        request.session.pop("printify_shops_%s" % pk, None)
        self.message_user(request, _("Shop selected successfully. You can now test connection or sync products."))
        return self._redirect(pk)

    def _test_view(self, request, pk):
        cfg, err = self._guard(request, pk)
        if err:
            return err
        self._test_one(request, cfg)
        return self._redirect(pk)

    def _sync_view(self, request, pk):
        cfg, err = self._guard(request, pk)
        if err:
            return err
        from .services import import_catalog_from_config
        report, _log = import_catalog_from_config(cfg, apply=True)
        if report.get("error"):
            self.message_user(request, _("Sync failed: %(e)s") % {"e": report["error"]}, level="error")
        elif report["created"] == 0 and report["updated"] == 0:
            self.message_user(request, _("Sync finished but imported 0 products (%(s)d skipped for "
                              "missing id/title). The shop may be empty or all products are drafts.")
                              % {"s": report["skipped"]}, level="warning")
        else:
            self.message_user(request, _("Sync done: %(c)d created, %(u)d updated, %(h)d hidden "
                              "(no price — can't be sold), %(r)d need review. See the report below.")
                              % {"c": report["created"], "u": report["updated"], "h": report["hidden"],
                                 "r": len(report["to_review"])})
        return self._redirect(pk)

    def _dryrun_view(self, request, pk):
        cfg, err = self._guard(request, pk)
        if err:
            return err
        from .services import import_catalog_from_config
        report, _log = import_catalog_from_config(cfg, apply=False)
        if report.get("error"):
            self.message_user(request, _("Dry-run failed: %(e)s") % {"e": report["error"]}, level="error")
        else:
            self.message_user(request, _("Dry-run: would create %(c)d, update %(u)d "
                              "(missing price %(mp)d, missing image %(mi)d).") % {"c": report["created"],
                              "u": report["updated"], "mp": report["missing_price"], "mi": report["missing_image"]})
        return self._redirect(pk)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        cfg = PrintifyAccountConfig.objects.filter(pk=object_id).first()
        if cfg:
            extra_context["gl_token_present"] = cfg.has_token()
            extra_context["gl_has_shop"] = cfg.has_valid_shop()
            extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
            shops = list(request.session.get("printify_shops_%s" % object_id, []))
            hint = (cfg.shop_id or "").strip().lower()
            for s in shops:
                s["suggested"] = bool(hint and not hint.isdigit()
                                      and s.get("title", "").strip().lower() == hint)
            extra_context["gl_shops"] = shops
        return super().change_view(request, object_id, form_url, extra_context)

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
    """Read-only 'Sync Monitor' for the production-safe sync daemon (no token, no PII).

    This is a technical health page — it is deliberately not editable (the lock/backoff are
    managed by the daemon). It answers 'is the background sync healthy?'; the per-import result
    lives on the Printify account page."""
    list_display = ("monitor", "last_tick_at", "backoff_until", "consecutive_errors",
                    "products_synced_total", "updated_at")
    readonly_fields = ["monitor_explain"] + [f.name for f in PrintifySyncState._meta.fields]
    fieldsets = (
        (_("What is this?"), {"fields": ("monitor_explain",)}),
        (_("Health"), {"fields": ("last_tick_at", "last_full_sync_at", "backoff_until",
                                  "backoff_level", "consecutive_errors", "last_error_at",
                                  "last_error_status", "products_synced_total",
                                  "last_tick_synced", "last_tick_requests", "updated_at")}),
        (_("Lock (technical)"), {"fields": ("locked_at", "locked_by"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False        # readonly — the daemon owns this state, not the UI

    @admin.display(description=_("About the Sync Monitor"))
    def monitor_explain(self, obj):
        from django.utils.safestring import mark_safe
        recent = SyncLog.objects.filter(kind=SyncLog.KIND_PRODUCTS).order_by("-started_at")[:8]
        rows = ["<div style='max-width:640px;line-height:1.6;'>",
                "<p style='margin:.2rem 0;'>%s</p>" % _(
                    "This page tracks the state of the background/manual Printify sync: when it "
                    "last ran, whether it is in a rate-limit backoff, and how many errors it hit. "
                    "It is read-only — the daemon manages the lock and backoff."),
                "<div style='margin:.5rem 0;font-size:.85em;'>"
                "<a href='/admin/printify_integration/printifyaccountconfig/' style='color:var(--gl-gold,#a6824c);'>%s</a>"
                " &nbsp;·&nbsp; <a href='/admin/store/product/?is_available__exact=0' style='color:var(--gl-gold,#a6824c);'>%s</a>"
                "</div>" % (_("Back to Printify account (run sync)"), _("Products needing review"))]
        if recent:
            rows.append("<div style='font-weight:600;margin-top:.4rem;'>%s</div><ul style='margin:.2rem 0 0 1rem;font-size:.85em;'>" % _("Recent product syncs"))
            for lg in recent:
                rows.append("<li>%s — %s</li>" % (lg.started_at.strftime("%Y-%m-%d %H:%M"),
                                                  (lg.message or "—")[:120]))
            rows.append("</ul>")
        rows.append("</div>")
        return mark_safe("".join(rows))

    @admin.display(description=_("Sync daemon"))
    def monitor(self, obj):
        snap = status_snapshot()
        on = snap["enabled"]
        color = "#16a34a" if on else "#64748b"
        label = _("ENABLED") if on else _("disabled")
        extra = " · BACKOFF" if snap["backoff_active"] else ""
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;">{}</span> &nbsp;stale: {}{}',
            color, label, snap["stale_products"], extra)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("kind", "status_badge", "created_count", "updated_count", "hidden_count",
                    "skipped_count", "error_count", "duration_display", "started_at")
    list_filter = ("kind", "status", "dry_run")
    readonly_fields = ["report_detail"] + [f.name for f in SyncLog._meta.fields]
    fieldsets = (
        (_("Report"), {"fields": ("report_detail",)}),
        (_("Counts"), {"fields": ("kind", "status", "dry_run", "shop_id", "created_count",
                                  "updated_count", "hidden_count", "skipped_count",
                                  "missing_price_count", "missing_image_count", "error_count")}),
        (_("Timing"), {"fields": ("started_at", "finished_at", "message")}),
        (_("Raw detail"), {"fields": ("detail",), "classes": ("collapse",)}),
    )
    actions = ["run_product_sync", "run_order_pull"]

    @admin.display(description=_("Sync report"))
    def report_detail(self, obj):
        from django.utils.safestring import mark_safe
        det = obj.detail or {}
        rows = ["<div style='max-width:680px;line-height:1.6;'>"]
        rows.append("<p style='margin:.2rem 0;'>%s: <strong>%s</strong> · shop <code>%s</code>%s</p>" % (
            _("Operation"), obj.get_kind_display(), obj.shop_id or "—",
            " · DRY-RUN" if obj.dry_run else ""))
        rows.append("<p style='margin:.2rem 0;'>%s</p>" % (obj.message or "—"))
        to_review = det.get("to_review") or []
        if to_review:
            rows.append("<div style='font-weight:600;margin-top:.4rem;'>%s (%d)</div>" % (
                _("Products needing review"), len(to_review)))
            rows.append("<ul style='margin:.2rem 0 0 1rem;font-size:.86em;'>")
            for it in to_review[:60]:
                if isinstance(it, dict):
                    slug = it.get("slug", ""); pid = it.get("id")
                    why = ", ".join(it.get("reasons", [])) or "review"
                    hid = " · hidden" if it.get("hidden") else ""
                    link = ("/admin/store/product/%s/change/" % pid) if pid else "#"
                    rows.append("<li><a href='%s' style='color:var(--gl-gold,#a6824c);'>%s</a> — %s%s</li>"
                                % (link, slug, why, hid))
                else:
                    rows.append("<li>%s</li>" % it)
            rows.append("</ul>")
        samples = det.get("samples") or []
        if samples:
            rows.append("<div style='font-weight:600;margin-top:.4rem;'>%s</div><ul style='margin:.2rem 0 0 1rem;font-size:.86em;'>" % _("Sample products"))
            for s in samples[:8]:
                rows.append("<li>%s — price %s — %s</li>" % (
                    s.get("title", "?"), s.get("price", "?"),
                    _("has image") if s.get("has_image") else _("no image")))
            rows.append("</ul>")
        rows.append("</div>")
        return mark_safe("".join(rows))

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
