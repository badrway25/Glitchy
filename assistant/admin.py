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
    list_display = ("id", "account", "language", "created_at")
    list_filter = ("language", "created_at")
    readonly_fields = ("session_key", "account", "language", "ip_hash", "created_at")
    inlines = [AssistantMessageInline]


@admin.register(AssistantFeedback)
class AssistantFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "helpful", "created_at")
    list_filter = ("helpful", "created_at")
