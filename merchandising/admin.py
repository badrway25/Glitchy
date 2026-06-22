from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

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
    list_display = ("name", "featured", "mood", "season", "product_count",
                    "completeness_badge", "is_active", "order", "updated_at")
    list_filter = ("is_active", "featured", "mood", "season")
    list_editable = ("is_active", "featured", "order")
    search_fields = ("name", "subtitle", "hero_title", "editorial_intro")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("products",)
    readonly_fields = ("collection_preview", "created_at", "updated_at")
    actions = ["mark_featured", "unmark_featured"]
    fieldsets = (
        ("Content", {"fields": ("name", "slug", "image", "is_active", "featured", "order",
                                "collection_preview")}),
        ("Mood & season", {"fields": ("mood", "season")}),
        ("Editorial — English", {"fields": ("hero_title", "subtitle", "editorial_intro")}),
        ("Editorial — Italiano", {"fields": ("hero_title_it", "subtitle_it", "editorial_intro_it")}),
        ("Editorial — Français", {"fields": ("hero_title_fr", "subtitle_fr", "editorial_intro_fr")}),
        ("SEO", {"fields": ("seo_title", "meta_description")}),
        ("Products", {"fields": ("products",)}),
        ("Meta", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Pieces"))
    def product_count(self, obj):
        return obj.products.count()

    @admin.display(description=_("Completeness"))
    def completeness_badge(self, obj):
        c = obj.completeness()
        s = c["score"]
        color = "#16a34a" if s >= 80 else ("#d97706" if s >= 50 else "#dc2626")
        return format_html('<strong style="color:{}">{}%</strong>', color, s)

    @admin.display(description=_("Preview"))
    def collection_preview(self, obj):
        if not obj.pk:
            return "—"
        c = obj.completeness()
        pr = obj.price_range()
        miss = ", ".join(c["missing"]) or "—"
        img = (f'<img src="{obj.image}" style="max-height:90px;border-radius:8px;margin-bottom:8px;">'
               if obj.image else "")
        return format_html(
            '<div style="font-size:13px;line-height:1.6;">{}'
            '<div>Quality: <b>{}%</b> · Pieces: <b>{}</b> · Price: {} · Colours: {}</div>'
            '<div>Mood: <b>{}</b> · Season: <b>{}</b></div>'
            '<div style="color:#dc2626;">Missing: {}</div>'
            '<div><a href="{}" target="_blank">Open public page ↗</a></div></div>',
            mark_safe(img), c["score"], obj.products.count(),
            (f"{pr[0]:.0f}–{pr[1]:.0f}" if pr else "—"), ", ".join(obj.main_colors()) or "—",
            obj.get_mood_display() or "—", obj.get_season_display() or "—", miss, obj.get_url())

    @admin.action(description=_("Mark selected as featured"))
    def mark_featured(self, request, queryset):
        n = queryset.update(featured=True)
        self.message_user(request, _("%(n)d collection(s) featured.") % {"n": n})

    @admin.action(description=_("Remove featured from selected"))
    def unmark_featured(self, request, queryset):
        n = queryset.update(featured=False)
        self.message_user(request, _("%(n)d collection(s) un-featured.") % {"n": n})


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
    from greatkart.admin_pii import masked_email_column
    masked_email = masked_email_column("email")
    list_display = ("masked_email", "product", "notify_type", "notified", "created_at")
    list_filter = ("notify_type", "notified", "created_at")
    search_fields = ("email", "product__product_name")
    readonly_fields = ("email", "product", "variant", "notify_type", "consent",
                       "ip_hash", "created_at")

    def has_add_permission(self, request):
        return False
