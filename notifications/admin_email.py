"""Mail Control Center admin — email/SMTP config, secrets encrypted, write-only,
masked, superadmin-gated, with a rate-limited superadmin-only test-send.

Mirrors the Payment/Printify secure-config admin: PasswordInput write-only fields
guarantee no secret reaches the browser; masked last-4 + fingerprint prove presence;
Test-send is POST-only, superadmin-gated and rate-limited. Nothing here is used
until ``is_enabled`` is turned on — the app falls back to the server env otherwise.
"""
from django import forms
from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
except Exception:                       # graceful fallback if Unfold is absent
    from django.contrib.admin import ModelAdmin as BaseModelAdmin

from . import secrets as secretbox
from .models import EmailConfiguration

#: how many test-sends a superadmin may trigger before a short cooldown
_TEST_MAX = 5
_TEST_WINDOW = 600                      # seconds

# write-only form field -> encrypted secret slot
_SECRET_FIELDS = {
    "new_smtp_password": "smtp_password",
    "new_n8n_secret": "n8n_secret",
}


def _is_superadmin(user):
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_superuser", False))


class EmailConfigurationForm(forms.ModelForm):
    new_smtp_password = forms.CharField(
        required=False, label=_("Set / replace SMTP password"),
        widget=forms.PasswordInput(render_value=False,
                                   attrs={"autocomplete": "new-password"}),
        help_text=_("Write-only. Leave blank to keep the current password. Encrypted at rest, never shown again."))
    new_n8n_secret = forms.CharField(
        required=False, label=_("Set / replace n8n shared secret"),
        widget=forms.PasswordInput(render_value=False,
                                   attrs={"autocomplete": "new-password"}),
        help_text=_("Write-only. Only needed if you route mail through an n8n webhook configured here."))

    class Meta:
        model = EmailConfiguration
        fields = ("is_enabled", "provider", "support_email", "admin_notify_email",
                  "default_from_email", "reply_to_email", "smtp_host", "smtp_port",
                  "smtp_use_tls", "smtp_use_ssl", "smtp_username",
                  "n8n_mail_enabled", "n8n_webhook_url")

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
                _("PAYMENT_CONFIG_KEY is not configured on the server — cannot encrypt "
                  "the secret. Set it in the environment first."))
        return val

    def clean_new_smtp_password(self):
        return self._clean_secret("new_smtp_password")

    def clean_new_n8n_secret(self):
        return self._clean_secret("new_n8n_secret")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("smtp_use_tls") and cleaned.get("smtp_use_ssl"):
            raise forms.ValidationError(
                _("TLS and SSL cannot both be enabled — choose one."))
        provider = cleaned.get("provider")
        if provider == EmailConfiguration.PROVIDER_SMTP:
            port = cleaned.get("smtp_port")
            if port is not None and not (1 <= int(port) <= 65535):
                self.add_error("smtp_port", _("Enter a port between 1 and 65535."))
            if cleaned.get("is_enabled") and not (cleaned.get("smtp_host") or "").strip():
                self.add_error("smtp_host",
                               _("An SMTP host is required to send via SMTP."))
        if provider == EmailConfiguration.PROVIDER_N8N and cleaned.get("n8n_mail_enabled"):
            if not (cleaned.get("n8n_webhook_url") or "").strip():
                self.add_error("n8n_webhook_url",
                               _("An n8n webhook URL is required for n8n mail."))
        return cleaned


@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(BaseModelAdmin):
    form = EmailConfigurationForm
    change_form_template = "admin/notifications/emailconfiguration/change_form.html"
    list_display = ("__str__", "provider", "is_enabled", "status_badge", "updated_at")
    readonly_fields = ("smtp_password_state", "n8n_secret_state", "resolved_state",
                       "test_state", "created_at", "updated_at")

    _SMTP_HELP = _("SMTP transport. The password is write-only and encrypted at rest. "
                   "TLS is the usual choice on port 587; SSL on 465. Leave the password "
                   "blank to keep the current one.")
    _N8N_HELP = _("Optional: route mail through an n8n webhook set here instead of the "
                  "server env. Leave disabled to keep using the env-configured n8n.")
    fieldsets = (
        (_("Status"), {"fields": ("is_enabled", "provider", "resolved_state")}),
        (_("Addresses"), {"fields": ("support_email", "admin_notify_email",
                                     "default_from_email", "reply_to_email")}),
        (_("SMTP transport"), {"description": _SMTP_HELP,
                               "fields": ("smtp_host", "smtp_port", "smtp_use_tls",
                                          "smtp_use_ssl", "smtp_username",
                                          "new_smtp_password", "smtp_password_state")}),
        (_("n8n mail (optional)"), {"description": _N8N_HELP,
                                    "fields": ("n8n_mail_enabled", "n8n_webhook_url",
                                               "new_n8n_secret", "n8n_secret_state")}),
        (_("Test"), {"fields": ("test_state",)}),
        (_("Meta"), {"fields": ("created_at", "updated_at")}),
    )
    _ADD_HIDDEN = frozenset({"created_at", "updated_at", "smtp_password_state",
                             "n8n_secret_state", "resolved_state", "test_state"})

    # ---- singleton -----------------------------------------------------------
    def has_add_permission(self, request):
        if not _is_superadmin(request.user):
            return False
        return not EmailConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_fieldsets(self, request, obj=None):
        is_add = obj is None
        drop = set() if _is_superadmin(request.user) else set(_SECRET_FIELDS)
        cleaned = []
        for title, opts in self.fieldsets:
            fields = tuple(f for f in opts["fields"]
                           if f not in drop and not (is_add and f in self._ADD_HIDDEN))
            if fields:
                cleaned.append((title, {**opts, "fields": fields}))
        return tuple(cleaned)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not _is_superadmin(request.user):
            ro += ["is_enabled", "provider", "smtp_host", "smtp_port", "smtp_use_tls",
                   "smtp_use_ssl", "smtp_username", "n8n_mail_enabled", "n8n_webhook_url"]
        return ro

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _is_superadmin(request.user):
            for f in _SECRET_FIELDS:
                form.base_fields.pop(f, None)
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        by = getattr(request.user, "email", "") or str(request.user)
        obj.updated_by = str(by)[:150]
        if _is_superadmin(request.user):
            dirty = False
            for field, slot in _SECRET_FIELDS.items():
                val = (form.cleaned_data.get(field) or "").strip()
                if val:
                    obj.set_secret(slot, val, by=by)
                    dirty = True
            if dirty:
                obj.save()
        obj.save(update_fields=["updated_by"])

    # ---- masked / status displays (never the secret) -------------------------
    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        s = obj.last_test_status
        colors = {"connected": "#16a34a", "failed": "#dc2626", "skipped": "#64748b"}
        label = s or _("not tested")
        return mark_safe('<span style="background:%s;color:#fff;padding:2px 8px;border-radius:999px;'
                         'font-size:11px;font-weight:600;">%s</span>' % (colors.get(s, "#94a3b8"), label))

    def _secret_state(self, obj, slots):
        if obj is None or not obj.pk:
            return _("Not saved yet — enter the credentials above and Save.")
        rows = ["<div>%s: <code>%s</code></div>" % (label, obj.secret_display(name))
                for name, label in slots]
        if obj.secret_updated_by:
            rows.append("<div style='opacity:.7;font-size:.85em;'>%s: %s</div>"
                        % (_("Updated by"), obj.secret_updated_by))
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(rows))

    @admin.display(description=_("SMTP password status"))
    def smtp_password_state(self, obj):
        return self._secret_state(obj, [("smtp_password", _("SMTP password"))])

    @admin.display(description=_("n8n secret status"))
    def n8n_secret_state(self, obj):
        return self._secret_state(obj, [("n8n_secret", _("n8n shared secret"))])

    @admin.display(description=_("Resolved configuration"))
    def resolved_state(self, obj):
        from .email_settings import (get_admin_notify_email, get_default_from_email,
                                     is_email_configured, get_public_support_email)
        yes = "<span style='color:#16a34a;font-weight:700;'>%s</span>"
        no = "<span style='color:#b3554e;font-weight:700;'>%s</span>"
        support = get_public_support_email()
        rows = [
            "<div>%s: %s</div>" % (_("Support address shown to customers"),
                                   (yes % support) if support else (no % _("hidden (placeholder)"))),
            "<div>%s: %s</div>" % (_("Admin-notify recipient"),
                                   yes % (get_admin_notify_email() or "—")),
            "<div>%s: %s</div>" % (_("From address"),
                                   yes % (get_default_from_email() or _("Django default"))),
            "<div style='margin-top:.35rem;'>%s: <strong>%s</strong></div>" % (
                _("Email configured"), _("yes") if is_email_configured() else _("no")),
        ]
        if not secretbox.has_key():
            rows.append("<div style='margin-top:.4rem;color:#b45309;font-weight:600;'>%s</div>"
                        % _("PAYMENT_CONFIG_KEY is not set — secrets cannot be saved until it is."))
        if obj is None or not obj.is_enabled:
            rows.append("<div style='margin-top:.4rem;opacity:.75;'>%s</div>"
                        % _("This config is disabled — the server env is used instead."))
        return mark_safe("<div style='line-height:1.7;'>%s</div>" % "".join(rows))

    @admin.display(description=_("Last test"))
    def test_state(self, obj):
        if obj is None or not obj.pk or not obj.last_test_at:
            return _("Never tested. Save, then use 'Send test email'.")
        color = "#16a34a" if obj.last_test_status == "connected" else (
            "#64748b" if obj.last_test_status == "skipped" else "#dc2626")
        parts = ["<div><span style='color:%s;font-weight:700;'>%s</span></div>" % (
            color, obj.last_test_status or "—")]
        if obj.last_test_detail_safe:
            parts.append("<div style='opacity:.8;'>%s</div>" % obj.last_test_detail_safe)
        if obj.last_test_error_safe:
            parts.append("<div style='color:#b3554e;'>%s</div>" % obj.last_test_error_safe)
        parts.append("<div style='opacity:.6;font-size:.82em;'>%s</div>"
                     % obj.last_test_at.strftime("%Y-%m-%d %H:%M"))
        return mark_safe("<div style='line-height:1.6;'>%s</div>" % "".join(parts))

    # ---- test-send (POST, superadmin, rate-limited) --------------------------
    def get_urls(self):
        from django.urls import path
        base = "notifications_emailconfiguration"
        return [
            path("<int:pk>/send-test/", self.admin_site.admin_view(self._test_view),
                 name="%s_test" % base),
        ] + super().get_urls()

    def _rate_limited(self, request) -> bool:
        try:
            from django.core.cache import cache
            key = "mailtest_rl:%s" % getattr(request.user, "pk", "anon")
            n = cache.get(key, 0)
            if n >= _TEST_MAX:
                return True
            cache.set(key, n + 1, _TEST_WINDOW)
        except Exception:
            return False
        return False

    def _test_view(self, request, pk):
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        if request.method != "POST":
            return redirect("admin:notifications_emailconfiguration_change", pk)
        if not _is_superadmin(request.user):
            return HttpResponseForbidden("Superadmin only.")
        if self._rate_limited(request):
            self.message_user(request, _("Too many test sends — please wait a few minutes."),
                              level=messages.WARNING)
            return redirect("admin:notifications_emailconfiguration_change", pk)
        cfg = EmailConfiguration.objects.filter(pk=pk).first()
        if cfg:
            from .email_settings import send_test_email
            recipient = (cfg.admin_notify_email or cfg.support_email
                         or getattr(request.user, "email", ""))
            by = getattr(request.user, "email", "") or str(request.user)
            res = send_test_email(cfg, recipient, requested_by=by)
            if res["ok"] and res["status"] == "connected":
                self.message_user(request, _("Test email sent — %(d)s") % {"d": res["detail"]})
            elif res["status"] == "skipped":
                self.message_user(request, res["detail"], level=messages.INFO)
            else:
                self.message_user(request, _("Test failed — %(e)s") % {"e": res["error"] or "error"},
                                  level=messages.ERROR)
        return redirect("admin:notifications_emailconfiguration_change", pk)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        cfg = EmailConfiguration.objects.filter(pk=object_id).first()
        extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
        extra_context["gl_can_test"] = bool(cfg and cfg.is_enabled
                                            and cfg.provider != EmailConfiguration.PROVIDER_DISABLED)
        return super().change_view(request, object_id, form_url, extra_context)
