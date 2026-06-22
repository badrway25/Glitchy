from django.contrib import admin

from .models import (Collection, Outfit, ProductNotificationSignup, ProductRelation)


@admin.register(ProductRelation)
class ProductRelationAdmin(admin.ModelAdmin):
    list_display = ("from_product", "relation_type", "to_product", "order", "is_active")
    list_filter = ("relation_type", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("from_product__product_name", "to_product__product_name")
    raw_id_fields = ("from_product", "to_product")


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "featured", "order")
    list_filter = ("is_active", "featured")
    list_editable = ("is_active", "featured", "order")
    search_fields = ("name", "subtitle", "hero_title")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("products",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "image", "meta_description", "is_active",
                           "featured", "order", "products")}),
        ("English", {"fields": ("hero_title", "subtitle")}),
        ("Italiano", {"fields": ("hero_title_it", "subtitle_it")}),
        ("Français", {"fields": ("hero_title_fr", "subtitle_fr")}),
    )


@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ("title", "anchor_product", "is_active", "featured", "order")
    list_filter = ("is_active", "featured")
    list_editable = ("is_active", "featured", "order")
    search_fields = ("title", "description")
    raw_id_fields = ("anchor_product",)
    filter_horizontal = ("products",)
    fieldsets = (
        (None, {"fields": ("image", "anchor_product", "is_active", "featured", "order", "products")}),
        ("English", {"fields": ("title", "description")}),
        ("Italiano", {"fields": ("title_it", "description_it")}),
        ("Français", {"fields": ("title_fr", "description_fr")}),
    )


@admin.register(ProductNotificationSignup)
class ProductNotificationSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "product", "notify_type", "notified", "created_at")
    list_filter = ("notify_type", "notified", "created_at")
    search_fields = ("email", "product__product_name")
    readonly_fields = ("email", "product", "variant", "notify_type", "consent",
                       "ip_hash", "created_at")

    def has_add_permission(self, request):
        return False
