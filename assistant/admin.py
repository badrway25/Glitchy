from django.contrib import admin

from .models import (AssistantConversation, AssistantFeedback,
                     AssistantMessage, KnowledgeEntry)


@admin.register(KnowledgeEntry)
class KnowledgeEntryAdmin(admin.ModelAdmin):
    list_display = ("key", "category", "question", "priority", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    list_editable = ("priority", "is_active")
    search_fields = ("key", "question", "answer", "keywords")
    fieldsets = (
        (None, {"fields": ("key", "category", "priority", "is_active", "keywords")}),
        ("English", {"fields": ("question", "answer")}),
        ("Italiano", {"fields": ("question_it", "answer_it")}),
        ("Français", {"fields": ("question_fr", "answer_fr")}),
    )


class AssistantMessageInline(admin.TabularInline):
    model = AssistantMessage
    extra = 0
    readonly_fields = ("role", "content", "provider", "grounded", "used_sources", "created_at")
    can_delete = False


@admin.register(AssistantConversation)
class AssistantConversationAdmin(admin.ModelAdmin):
    from greatkart.admin_pii import masked_user_email_column
    masked_account = masked_user_email_column("account")
    list_display = ("id", "masked_account", "language", "created_at")
    list_filter = ("language", "created_at")
    readonly_fields = ("session_key", "account", "language", "ip_hash", "created_at")
    inlines = [AssistantMessageInline]


@admin.register(AssistantFeedback)
class AssistantFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "helpful", "created_at")
    list_filter = ("helpful", "created_at")


# --------------------------------------------------------------------------- #
# OpenAI configuration — same encrypted control-center pattern as payments/Google
# --------------------------------------------------------------------------- #
from django import forms
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from payments import secrets as secretbox

from .models import AssistantConfig


def _is_superadmin(user):
    return bool(getattr(user, "is_superadmin", False) or getattr(user, "is_superuser", False))



class AssistantConfigForm(forms.ModelForm):
    new_api_key = forms.CharField(
        label=_("Set / replace OpenAI API key"), required=False, max_length=256,
        widget=forms.PasswordInput(render_value=False,
                                   attrs={"placeholder": "sk-...", "autocomplete": "new-password"}),
        help_text=_("Write-only. Leave blank to keep the current key. Encrypted at rest, "
                    "never shown again."))

    class Meta:
        model = AssistantConfig
        fields = ["is_enabled", "model", "temperature", "max_input_chars",
                  "max_output_tokens", "rate_limit_per_session", "system_prompt_extra"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from unfold.widgets import INPUT_CLASSES, CHECKBOX_CLASSES, SELECT_CLASSES
        except Exception:
            return
        text = " ".join(INPUT_CLASSES)
        checkbox = " ".join(CHECKBOX_CLASSES)
        sel = " ".join(SELECT_CLASSES)
        for field in self.fields.values():
            w = field.widget
            cur = w.attrs.get("class", "")
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (cur + " " + checkbox).strip()
            elif isinstance(w, forms.Select):
                w.attrs["class"] = (cur + " " + sel).strip()
            elif isinstance(w, (forms.TextInput, forms.PasswordInput, forms.NumberInput,
                                forms.Textarea)):
                w.attrs["class"] = (cur + " " + text).strip()

    def clean_new_api_key(self):
        val = (self.cleaned_data.get("new_api_key") or "").strip()
        if val and not secretbox.has_key():
            raise forms.ValidationError(
                _("Encryption key missing — the key was NOT saved (it is never stored in "
                  "plain text). Ask the server administrator to configure "
                  "PAYMENT_CONFIG_KEY, then try again."))
        return val

    def save(self, commit=True):
        obj = super().save(commit=False)
        val = self.cleaned_data.get("new_api_key") or ""
        if val:
            obj.set_api_key(val, by="admin")
        if commit:
            obj.save()
        return obj


@admin.register(AssistantConfig)
class AssistantConfigAdmin(admin.ModelAdmin):
    form = AssistantConfigForm
    change_form_template = "admin/assistant/assistantconfig/change_form.html"
    list_display = ("__str__", "is_enabled", "model", "key_state", "last_connection_status",
                    "updated_at")

    fieldsets = (
        (_("Status"), {"fields": ("is_enabled", "model", "temperature")}),
        (_("OpenAI API key — secret (encrypted)"), {
            "description": _("Write-only, encrypted at rest with the server encryption key "
                             "(PAYMENT_CONFIG_KEY). Only a fingerprint is shown after saving. "
                             "The key never reaches the browser or the logs. Never paste a "
                             "key anywhere else."),
            "fields": ("new_api_key", "key_state")}),
        (_("Assistant behaviour"), {
            "fields": ("system_prompt_extra", "max_input_chars", "max_output_tokens",
                       "rate_limit_per_session")}),
    )
    readonly_fields = ("key_state",)

    def key_state(self, obj):
        from django.utils.html import format_html
        if not obj or not obj.has_api_key():
            return format_html('<span style="opacity:.65;">{}</span>', _("No key saved yet."))
        return format_html("<code>{}</code> · {}", obj.api_key_display(),
                           obj.api_key_set_at.strftime("%Y-%m-%d %H:%M") if obj.api_key_set_at else "")
    key_state.short_description = _("Stored key")

    def has_add_permission(self, request):
        return _is_superadmin(request.user) and not AssistantConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return _is_superadmin(request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _is_superadmin(request.user) and "new_api_key" in form.base_fields:
            form.base_fields.pop("new_api_key")
        return form

    def get_fieldsets(self, request, obj=None):
        fs = super().get_fieldsets(request, obj)
        if _is_superadmin(request.user):
            return fs
        pruned = []
        for title, cfg in fs:
            fields = tuple(f for f in cfg.get("fields", ()) if f != "new_api_key")
            pruned.append((title, {**cfg, "fields": fields}))
        return pruned

    def get_urls(self):
        urls = super().get_urls()
        extra = [path("<int:object_id>/test/", self.admin_site.admin_view(self._test_view),
                      name="assistant_assistantconfig_test")]
        return extra + urls

    def _test_view(self, request, object_id):
        if request.method != "POST" or not _is_superadmin(request.user):
            return HttpResponseRedirect(
                reverse("admin:assistant_assistantconfig_change", args=[object_id]))
        cfg = AssistantConfig.objects.filter(pk=object_id).first()
        if cfg:
            from .services_openai import test_connection
            result = test_connection(cfg)
            if result["ok"]:
                messages.success(request, result["detail"])
            else:
                messages.error(request, result["error"])
        return HttpResponseRedirect(
            reverse("admin:assistant_assistantconfig_change", args=[object_id]))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
        cfg = AssistantConfig.objects.filter(pk=object_id).first()
        extra_context["gl_has_key"] = bool(cfg and cfg.has_api_key())
        extra_context["gl_secretbox_ready"] = secretbox.has_key()
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["gl_is_superadmin"] = _is_superadmin(request.user)
        extra_context["gl_secretbox_ready"] = secretbox.has_key()
        return super().add_view(request, form_url, extra_context)
