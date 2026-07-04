"""Checkout API settings admin — Google Maps/Places + Address Validation.

Same security model as the Payment Control Center: the server key is write-only
(PasswordInput, never rendered), Fernet-encrypted at rest, shown only as a masked
fingerprint; the dangerous switches are superadmin-only; Test connection is a POST-only,
superadmin-gated, READ-ONLY check (it validates a fixed dummy address — no mutation,
no order, no payment).
"""
from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
except Exception:
    from django.contrib.admin import ModelAdmin as BaseModelAdmin

from payments import secrets as secretbox

from .models import CheckoutApiConfig


def _is_superadmin(user):
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_superuser", False))


class CheckoutApiConfigForm(forms.ModelForm):
    new_server_key = forms.CharField(
        required=False, label=_("Set / replace Address Validation server key"),
        widget=forms.PasswordInput(render_value=False,
                                   attrs={"autocomplete": "new-password", "placeholder": "AIza…"}),
        help_text=_("Write-only. Leave blank to keep the current key. Encrypted at rest, never shown again."))

    class Meta:
        model = CheckoutApiConfig
        fields = ("is_enabled", "enable_autocomplete", "enable_address_validation",
                  "maps_browser_key", "allowed_domains_note")
        widgets = {"maps_browser_key": forms.TextInput(
            attrs={"placeholder": "AIza… (browser, referrer-restricted)"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from unfold.widgets import INPUT_CLASSES, CHECKBOX_CLASSES
        except Exception:
            return
        text, checkbox = " ".join(INPUT_CLASSES), " ".join(CHECKBOX_CLASSES)
        for field in self.fields.values():
            w = field.widget
            cur = w.attrs.get("class", "")
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (cur + " " + checkbox).strip()
            elif isinstance(w, (forms.TextInput, forms.PasswordInput)):
                w.attrs["class"] = (cur + " " + text).strip()

    def clean_new_server_key(self):
        val = (self.cleaned_data.get("new_server_key") or "").strip()
        if val and not secretbox.has_key():
            raise forms.ValidationError(
                _("Encryption key missing — the key was NOT saved (it is never stored in plain "
                  "text). Ask the server administrator to configure PAYMENT_CONFIG_KEY, then try again."))
        return val


@admin.register(CheckoutApiConfig)
class CheckoutApiConfigAdmin(BaseModelAdmin):
    form = CheckoutApiConfigForm
    change_form_template = "admin/shipping/checkoutapiconfig/change_form.html"
    list_display = ("__str__", "is_enabled", "enable_autocomplete", "enable_address_validation",
                    "connection_badge", "updated_at")
    readonly_fields = ("server_key_state", "connection_state", "created_at", "updated_at")
    fieldsets = (
        (_("Status"), {"fields": ("is_enabled", "enable_autocomplete", "enable_address_validation")}),
        (_("Google keys"), {
            "description": _("Browser key: Google Cloud console → Credentials → API key restricted "
                             "by HTTP referrer, Places API enabled (public by design). Server key: "
                             "a SEPARATE key restricted by IP, Address Validation API enabled — this "
                             "one is a secret and is stored encrypted."),
            "fields": ("maps_browser_key", "allowed_domains_note", "new_server_key", "server_key_state")}),
        (_("Connection status"), {"fields": ("connection_state",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return not CheckoutApiConfig.objects.exists()      # singleton

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not _is_superadmin(request.user):
            ro += ["is_enabled", "enable_autocomplete", "enable_address_validation"]
        return ro

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _is_superadmin(request.user):
            form.base_fields.pop("new_server_key", None)
        return form

    def get_fieldsets(self, request, obj=None):
        fs = super().get_fieldsets(request, obj)
        if _is_superadmin(request.user):
            return fs
        return tuple((t, {**o, "fields": tuple(f for f in o["fields"] if f != "new_server_key")})
                     for t, o in fs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not _is_superadmin(request.user):
            return
        val = (form.cleaned_data.get("new_server_key") or "").strip()
        if val:
            obj.set_server_key(val, by=getattr(request.user, "email", "") or str(request.user))
            obj.save()

    @admin.display(description=_("Connection"))
    def connection_badge(self, obj):
        s = obj.last_connection_status
        color = {"connected": "#16a34a", "failed": "#dc2626"}.get(s, "#64748b")
        return mark_safe('<span style="background:%s;color:#fff;padding:2px 8px;border-radius:999px;'
                         'font-size:11px;font-weight:600;">%s</span>' % (color, s or _("not tested")))

    @admin.display(description=_("Server key status"))
    def server_key_state(self, obj):
        if obj is None or not obj.pk:
            return _("Save first, then add the server key.")
        rows = ["<div>%s: <code>%s</code></div>" % (_("Address Validation key"), obj.server_key_display())]
        if obj.secret_updated_by:
            rows.append("<div style='opacity:.7;font-size:.85em;'>%s: %s</div>"
                        % (_("Updated by"), obj.secret_updated_by))
        return mark_safe("<div style='line-height:1.7;'>%s</div>" % "".join(rows))

    @admin.display(description=_("Connection status (read-only)"))
    def connection_state(self, obj):
        if obj is None or not obj.pk or not obj.last_connection_check_at:
            return _("Never tested. Use 'Test connection'.")
        color = "#16a34a" if obj.last_connection_status == "connected" else "#dc2626"
        parts = ["<div><strong style='color:%s;'>%s</strong></div>" % (color, obj.last_connection_status)]
        if obj.last_connection_detail_safe:
            parts.append("<div style='opacity:.8;'>%s</div>" % obj.last_connection_detail_safe)
        parts.append("<div style='opacity:.6;font-size:.82em;'>%s</div>"
                     % obj.last_connection_check_at.strftime("%Y-%m-%d %H:%M"))
        return mark_safe("<div style='line-height:1.7;'>%s</div>" % "".join(parts))

    # -- Test connection (POST, superadmin, read-only) --
    def get_urls(self):
        from django.urls import path
        return [path("<int:pk>/test-connection/", self.admin_site.admin_view(self._test_view),
                     name="shipping_checkoutapiconfig_test")] + super().get_urls()

    def _test_view(self, request, pk):
        from django.http import HttpResponseForbidden
        if request.method != "POST":
            return redirect("admin:shipping_checkoutapiconfig_change", pk)
        if not _is_superadmin(request.user):
            return HttpResponseForbidden("Superuser only.")
        cfg = CheckoutApiConfig.objects.filter(pk=pk).first()
        if cfg:
            from .address_validation import test_connection
            res = test_connection(cfg)
            if res["ok"]:
                self.message_user(request, _("Connection OK — %(d)s") % {"d": res["detail"]})
            else:
                self.message_user(request, _("Connection failed — %(e)s") % {"e": res["error"]}, level="error")
        return redirect("admin:shipping_checkoutapiconfig_change", pk)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        cfg = CheckoutApiConfig.objects.filter(pk=object_id).first()
        extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
        extra_context["gl_has_key"] = bool(cfg and cfg.has_server_key())
        extra_context["gl_secretbox_ready"] = secretbox.has_key()
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
        extra_context["gl_secretbox_ready"] = secretbox.has_key()
        return super().add_view(request, form_url, extra_context)
