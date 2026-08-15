from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .forms import SiteVisualAssetForm
from .models import AnalyticsEvent, Announcement, SiteVisualAsset
from .visuals import slot_config, visual_for


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("message", "is_active", "dismissible", "priority", "created_at")
    list_editable = ("is_active", "dismissible", "priority")
    fieldsets = (
        (None, {"fields": ("is_active", "dismissible", "priority")}),
        ("Message", {"fields": ("message", "message_it", "message_fr")}),
        ("Optional link", {"fields": ("link_url", "link_label", "link_label_it", "link_label_fr")}),
    )


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("name", "path", "created_at")
    list_filter = ("name", "created_at")
    search_fields = ("path", "session_key")
    readonly_fields = ("name", "path", "session_key", "meta", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(SiteVisualAsset)
class SiteVisualAssetAdmin(admin.ModelAdmin):
    """Homepage imagery, slot by slot.

    The changelist doubles as the control panel: each row shows the slot, a live
    preview, whether the image is the admin's or the shipped design, and the
    recommended size. Clearing `is_active` instantly restores the original."""

    form = SiteVisualAssetForm
    list_display = ("slot_label", "preview", "state_badge", "guidance", "alt_text",
                    "is_active", "updated_at")
    list_filter = ("is_active", "slot")
    readonly_fields = ("preview_pair", "guidance", "width", "height",
                       "created_at", "updated_at", "updated_by")
    fieldsets = (
        (None, {"fields": ("slot", "guidance", "is_active", "title")}),
        (_("Image"), {"fields": ("image", "mobile_image", "alt_text",
                                 "preview_pair")}),
        (_("Framing"), {
            "description": _("Focal point moves the crop instead of stretching the "
                             "image — 50/50 is centred."),
            "fields": ("focal_point_x", "focal_point_y")}),
        (_("Audit"), {"classes": ("collapse",),
                      "fields": ("width", "height", "created_at", "updated_at",
                                 "updated_by")}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = str(request.user)[:150]
        super().save_model(request, obj, form, change)

    @admin.display(description=_("Slot"), ordering="slot")
    def slot_label(self, obj):
        return str(slot_config(obj.slot).get("label") or obj.slot)

    @admin.display(description=_("Recommended size"))
    def guidance(self, obj):
        cfg = slot_config(obj.slot)
        if not cfg:
            return "—"
        return format_html(
            '<span style="font-size:12px;color:#64748b;">{}×{} px · {}</span>',
            cfg.get("recommended_width", 0), cfg.get("recommended_height", 0),
            cfg.get("help", ""))

    @admin.display(description=_("Preview"))
    def preview(self, obj):
        data = visual_for(obj.slot)
        if not data.get("url"):
            return "—"
        return format_html(
            '<img src="{}" style="width:110px;height:62px;object-fit:cover;'
            'object-position:{};border-radius:8px;" loading="lazy">',
            data["url"], data.get("object_position", "50% 50%"))

    @admin.display(description=_("Desktop / mobile preview"))
    def preview_pair(self, obj):
        data = visual_for(obj.slot)
        if not data.get("url"):
            return _("No image yet — the original design is in use.")
        mobile = data.get("mobile_url") or data["url"]
        return format_html(
            '<div style="display:flex;gap:18px;align-items:flex-end;">'
            '<figure style="margin:0;"><img src="{}" style="width:320px;height:150px;'
            'object-fit:cover;object-position:{};border-radius:10px;">'
            '<figcaption style="font-size:11px;color:#64748b;">Desktop</figcaption></figure>'
            '<figure style="margin:0;"><img src="{}" style="width:110px;height:200px;'
            'object-fit:cover;object-position:{};border-radius:10px;">'
            '<figcaption style="font-size:11px;color:#64748b;">Mobile 390</figcaption>'
            '</figure></div>',
            data["url"], data.get("object_position", "50% 50%"),
            mobile, data.get("object_position", "50% 50%"))

    @admin.display(description=_("State"))
    def state_badge(self, obj):
        custom = visual_for(obj.slot).get("is_custom")
        color, label = ("#16a34a", _("Custom")) if custom else ("#64748b", _("Default"))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>', color, label)
