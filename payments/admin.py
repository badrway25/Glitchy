"""Payment Control Center admin — secrets encrypted, write-only, masked, superadmin-gated.

Mirrors the Printify secure-config admin: the PasswordInput write-only fields guarantee no
secret ciphertext/plaintext reaches the browser; masked last-4 + fingerprint prove presence;
Test-connection is a POST-only, superadmin-gated, read-only action. Safe defaults stay OFF.
"""
from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
except Exception:                       # graceful fallback if Unfold is absent
    from django.contrib.admin import ModelAdmin as BaseModelAdmin

from . import secrets as secretbox
from .models import PaymentEvent, PaymentProviderConfig


def _is_superadmin(user):
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_superuser", False))


# secret slot -> the write-only form field name that sets it
_SECRET_FIELDS = {
    "new_stripe_secret_key": "stripe_secret_key",
    "new_stripe_webhook_secret": "stripe_webhook_secret",
    "new_paypal_secret": "paypal_secret",
}


class PaymentProviderConfigForm(forms.ModelForm):
    new_stripe_secret_key = forms.CharField(
        required=False, label=_("Set / replace Stripe secret key"),
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Write-only. Leave blank to keep the current key. Encrypted at rest, never shown again."))
    new_stripe_webhook_secret = forms.CharField(
        required=False, label=_("Set / replace Stripe webhook signing secret"),
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Write-only. Used to verify webhook signatures."))
    new_paypal_secret = forms.CharField(
        required=False, label=_("Set / replace PayPal client secret"),
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Write-only. Encrypted at rest, never shown again."))

    class Meta:
        model = PaymentProviderConfig
        fields = ("provider", "display_name", "is_enabled", "environment", "currency",
                  "stripe_publishable_key", "paypal_client_id", "paypal_api_base",
                  "allow_checkout", "allow_live_mode")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from unfold.widgets import INPUT_CLASSES, SELECT_CLASSES, CHECKBOX_CLASSES
        except Exception:
            return
        text, select, checkbox = " ".join(INPUT_CLASSES), " ".join(SELECT_CLASSES), " ".join(CHECKBOX_CLASSES)
        for field in self.fields.values():
            w = field.widget
            cur = w.attrs.get("class", "")
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (cur + " " + checkbox).strip()
            elif isinstance(w, forms.Select):
                w.attrs["class"] = (cur + " " + select).strip()
            elif isinstance(w, (forms.TextInput, forms.NumberInput, forms.PasswordInput,
                                forms.EmailInput, forms.URLInput, forms.Textarea)):
                w.attrs["class"] = (cur + " " + text).strip()

    def _clean_secret(self, field):
        val = (self.cleaned_data.get(field) or "").strip()
        if val and not secretbox.has_key():
            raise forms.ValidationError(
                _("PAYMENT_CONFIG_KEY is not configured on the server — cannot encrypt the secret. "
                  "Set it in the environment first."))
        return val

    def clean_new_stripe_secret_key(self):
        return self._clean_secret("new_stripe_secret_key")

    def clean_new_stripe_webhook_secret(self):
        return self._clean_secret("new_stripe_webhook_secret")

    def clean_new_paypal_secret(self):
        return self._clean_secret("new_paypal_secret")


@admin.register(PaymentProviderConfig)
class PaymentProviderConfigAdmin(BaseModelAdmin):
    form = PaymentProviderConfigForm
    change_form_template = "admin/payments/paymentproviderconfig/change_form.html"
    list_display = ("provider", "provider_badge", "is_enabled", "environment", "connection_badge", "updated_at")
    list_filter = ("provider", "is_enabled", "environment")
    readonly_fields = ("secret_state_detail", "payment_ops_panel", "connection_state_detail",
                       "created_at", "updated_at")

    add_fieldsets = (
        (_("Provider"), {"fields": ("provider", "display_name", "is_enabled", "environment", "currency"),
                         "description": _("Pick a provider and Save, then add credentials + test the connection.")}),
    )
    stripe_fieldsets = (
        (_("Provider"), {"fields": ("provider", "display_name", "is_enabled", "environment", "currency")}),
        (_("Stripe keys"), {"fields": ("stripe_publishable_key", "new_stripe_secret_key",
                                       "new_stripe_webhook_secret", "secret_state_detail")}),
        (_("Payment operations"), {"fields": ("payment_ops_panel",)}),
        (_("Safety gates"), {"fields": ("allow_checkout", "allow_live_mode")}),
        (_("Connection status"), {"fields": ("connection_state_detail",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )
    paypal_fieldsets = (
        (_("Provider"), {"fields": ("provider", "display_name", "is_enabled", "environment", "currency")}),
        (_("PayPal credentials"), {"fields": ("paypal_client_id", "paypal_api_base",
                                              "new_paypal_secret", "secret_state_detail")}),
        (_("Payment operations"), {"fields": ("payment_ops_panel",)}),
        (_("Safety gates"), {"fields": ("allow_checkout", "allow_live_mode")}),
        (_("Connection status"), {"fields": ("connection_state_detail",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            fs = self.add_fieldsets
        else:
            fs = self.paypal_fieldsets if obj.provider == PaymentProviderConfig.PAYPAL else self.stripe_fieldsets
        if _is_superadmin(request.user):
            return fs
        # non-superadmins never see the write-only secret fields
        cleaned = []
        for title, opts in fs:
            fields = tuple(f for f in opts["fields"] if f not in _SECRET_FIELDS)
            cleaned.append((title, {**opts, "fields": fields}))
        return tuple(cleaned)

    # -- permissions: only superadmins touch secrets + dangerous switches -----
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            ro.append("provider")           # provider is fixed after creation
        if not _is_superadmin(request.user):
            ro += ["allow_checkout", "allow_live_mode", "is_enabled", "environment"]
        return ro

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _is_superadmin(request.user):
            for f in _SECRET_FIELDS:
                form.base_fields.pop(f, None)
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not _is_superadmin(request.user):
            return
        by = getattr(request.user, "email", "") or str(request.user)
        dirty = False
        for field, slot in _SECRET_FIELDS.items():
            val = (form.cleaned_data.get(field) or "").strip()
            if val:
                obj.set_secret(slot, val, by=by)
                dirty = True
        if dirty:
            obj.save()

    # -- masked / status displays (never the secret) --------------------------
    @admin.display(description=_("Provider"))
    def provider_badge(self, obj):
        env = _("LIVE") if obj.is_live() else _("TEST")
        color = "#b45309" if obj.is_live() else "#64748b"
        return mark_safe('<span style="background:%s;color:#fff;padding:2px 8px;border-radius:999px;'
                         'font-size:11px;font-weight:700;">%s</span>' % (color, env))

    @admin.display(description=_("Connection"))
    def connection_badge(self, obj):
        s = obj.last_connection_status
        colors = {"connected": "#16a34a", "failed": "#dc2626"}
        label = s or _("not tested")
        return mark_safe('<span style="background:%s;color:#fff;padding:2px 8px;border-radius:999px;'
                         'font-size:11px;font-weight:600;">%s</span>' % (colors.get(s, "#64748b"), label))

    @admin.display(description=_("Secret status"))
    def secret_state_detail(self, obj):
        if obj is None or not obj.pk:
            return _("Save first, then add credentials.")
        rows = []
        slots = [("stripe_secret_key", _("Stripe secret key")),
                 ("stripe_webhook_secret", _("Webhook secret"))] if obj.provider == PaymentProviderConfig.STRIPE \
            else [("paypal_secret", _("PayPal secret"))]
        for name, label in slots:
            rows.append("<div>%s: <code>%s</code></div>" % (label, obj.secret_display(name)))
        if obj.secret_updated_by:
            rows.append("<div style='opacity:.7;font-size:.85em;'>%s: %s</div>"
                        % (_("Updated by"), obj.secret_updated_by))
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(rows))

    @admin.display(description=_("Connection status (read-only)"))
    def connection_state_detail(self, obj):
        if obj is None or not obj.pk or not obj.last_connection_check_at:
            return _("Never tested. Use 'Test connection'.")
        color = "#16a34a" if obj.last_connection_status == "connected" else "#dc2626"
        parts = ["<div><span style='color:%s;font-weight:700;'>%s</span></div>" % (
            color, obj.last_connection_status or "—")]
        if obj.last_connection_detail_safe:
            parts.append("<div style='opacity:.8;'>%s</div>" % obj.last_connection_detail_safe)
        if obj.last_connection_error_safe:
            parts.append("<div style='color:#b3554e;'>%s</div>" % obj.last_connection_error_safe)
        parts.append("<div style='opacity:.6;font-size:.82em;'>%s</div>" % obj.last_connection_check_at.strftime("%Y-%m-%d %H:%M"))
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(parts))

    @admin.display(description=_("Payment operations"))
    def payment_ops_panel(self, obj):
        if obj is None or not obj.pk:
            return _("Save first, then Test connection.")
        from payments import config as pc
        src = pc.stripe_source() if obj.provider == PaymentProviderConfig.STRIPE else pc.paypal_source()
        ready = obj.is_ready_for_checkout()
        rows = ["<div>%s: <strong>%s</strong></div>" % (_("Active credential source"), src.upper()),
                "<div>%s: <strong>%s</strong></div>" % (_("Ready for checkout"), _("yes") if ready else _("no")),
                "<div style='margin-top:.5rem;opacity:.7;font-size:.82em;'>%s</div>"
                % _("Test connection is read-only — it never creates a payment, capture or refund.")]
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(rows))

    # -- custom admin URLs (Test connection — POST, superadmin, read-only) ----
    def get_urls(self):
        from django.urls import path
        base = "payments_paymentproviderconfig"
        return [
            path("<int:pk>/test-connection/", self.admin_site.admin_view(self._test_view),
                 name="%s_test" % base),
        ] + super().get_urls()

    def _test_view(self, request, pk):
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        if request.method != "POST":
            return redirect("admin:payments_paymentproviderconfig_change", pk)
        if not _is_superadmin(request.user):
            return HttpResponseForbidden("Superuser only.")
        cfg = PaymentProviderConfig.objects.filter(pk=pk).first()
        if cfg:
            from .services import test_connection
            res = test_connection(cfg)
            if res["ok"]:
                self.message_user(request, _("Connection OK — %(d)s") % {"d": res["detail"]})
            else:
                self.message_user(request, _("Connection failed — %(e)s") % {"e": res["error"]}, level="error")
        return redirect("admin:payments_paymentproviderconfig_change", pk)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        cfg = PaymentProviderConfig.objects.filter(pk=object_id).first()
        if cfg:
            extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
            extra_context["gl_has_secret"] = (cfg.has_secret("stripe_secret_key")
                                              if cfg.provider == PaymentProviderConfig.STRIPE
                                              else cfg.has_secret("paypal_secret"))
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(PaymentEvent)
class PaymentEventAdmin(BaseModelAdmin):
    """Read-only safe payment monitor (no secrets, no card data, no full PII)."""
    list_display = ("created_at", "provider", "kind", "ok_badge", "status", "amount", "currency", "order_number")
    list_filter = ("provider", "kind", "ok")
    search_fields = ("external_id", "order_number", "payment_id")
    readonly_fields = [f.name for f in PaymentEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Result"))
    def ok_badge(self, obj):
        color = "#16a34a" if obj.ok else "#dc2626"
        label = _("ok") if obj.ok else _("fail")
        return mark_safe('<span style="background:%s;color:#fff;padding:2px 8px;border-radius:999px;'
                         'font-size:11px;font-weight:600;">%s</span>' % (color, label))
