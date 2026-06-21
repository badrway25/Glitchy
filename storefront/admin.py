from django.contrib import admin

from .models import AnalyticsEvent, Announcement


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
