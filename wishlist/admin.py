from django.contrib import admin

from .models import WishlistItem


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "saved_for_later", "created_at")
    list_filter = ("saved_for_later", "created_at")
    search_fields = ("product__product_name", "user__email")
    raw_id_fields = ("product", "user")
    readonly_fields = ("created_at",)
