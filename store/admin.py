from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import (GeneralFAQ, Product, ProductFAQ, ProductImage, ReviewRating, Variation)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class VariationInline(admin.TabularInline):
    model = Variation
    extra = 0
    fields = ("variation_category", "variation_value", "is_active",
              "printify_variant_id", "production_cost")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_name", "price", "base_cost", "margin_hint", "quality_score",
                    "stock", "category", "sync_badge", "is_available", "is_bestseller")
    list_filter = ("category", "is_available", "is_bestseller", "is_featured",
                   "printify_sync_status", "printify_visible")
    list_editable = ("is_available", "is_bestseller")
    search_fields = ("product_name", "sku", "printify_product_id")
    prepopulated_fields = {"slug": ("product_name",)}
    readonly_fields = ("printify_synced_at", "printify_sync_error", "printify_panel")
    inlines = [ProductImageInline, VariationInline]
    actions = ["resync_from_printify", "audit_data_quality"]
    fieldsets = (
        (None, {"fields": ("product_name", "slug", "category", "description")}),
        (_("Pricing & stock"), {"fields": ("price", "compare_at_price", "base_cost",
                                           "stock", "is_available")}),
        (_("Premium content"), {"fields": ("composition", "fit_notes", "care_instructions")}),
        (_("Merchandising"), {"fields": ("is_bestseller", "is_featured", "images")}),
        (_("Printify"), {"fields": ("printify_panel", "printify_product_id",
                                    "printify_blueprint_id", "printify_provider_id", "sku",
                                    "printify_blueprint_title", "printify_provider_name",
                                    "printify_options_summary", "printify_tags",
                                    "printify_visible", "printify_sync_status",
                                    "printify_synced_at", "printify_sync_error")}),
    )

    @admin.display(description=_("Quality"))
    def quality_score(self, obj):
        s = obj.data_quality_score()
        color = "#16a34a" if s >= 80 else ("#d97706" if s >= 50 else "#dc2626")
        return format_html('<strong style="color:{}">{}</strong>', color, f"{s}%")

    @admin.display(description=_("Printify data panel"))
    def printify_panel(self, obj):
        dq = obj.data_quality()
        variants = obj.variation_set.count() if hasattr(obj, "variation_set") else 0
        with_cost = obj.variation_set.filter(production_cost__gt=0).count() if variants else 0
        images = obj.gallery.count() if hasattr(obj, "gallery") else 0
        sc = dq["score"]
        scolor = "#16a34a" if sc >= 80 else ("#d97706" if sc >= 50 else "#dc2626")
        rows = mark_safe("".join(
            f'<tr><td style="padding:2px 10px 2px 0;">{c["key"]}</td>'
            f'<td style="color:{"#16a34a" if c["ok"] else "#dc2626"};">'
            f'{"✓" if c["ok"] else "✗"}</td></tr>' for c in dq["checks"]))
        return format_html(
            '<div style="font-size:13px;line-height:1.5;">'
            '<div style="font-size:22px;font-weight:800;color:{};margin-bottom:6px;">{}% '
            '<span style="font-size:12px;color:#64748b;font-weight:500;">data quality</span></div>'
            '<div>Blueprint: <b>{}</b> (#{}) · Provider: <b>{}</b> (#{})</div>'
            '<div>Options: {} · Visible: {} · Variants: <b>{}</b> ({} with cost) · Images: <b>{}</b></div>'
            '<table style="margin-top:8px;border-collapse:collapse;">{}</table></div>',
            scolor, sc, obj.printify_blueprint_title or "—", obj.printify_blueprint_id or "—",
            obj.printify_provider_name or "—", obj.printify_provider_id or "—",
            obj.printify_options_summary or "—", "yes" if obj.printify_visible else "no",
            variants, with_cost, images, rows)

    @admin.action(description=_("Audit data quality (selected)"))
    def audit_data_quality(self, request, queryset):
        from django.contrib import messages
        low = [p for p in queryset if p.data_quality_score() < 80]
        if low:
            names = ", ".join(f"{p.product_name[:24]} ({p.data_quality_score()}%)" for p in low[:10])
            self.message_user(request, _("%(n)d product(s) below 80%%: %(names)s") % {
                "n": len(low), "names": names}, level=messages.WARNING)
        else:
            self.message_user(request, _("All selected products are at 80%%+ data quality."),
                              level=messages.SUCCESS)

    @admin.display(description=_("Margin/unit"))
    def margin_hint(self, obj):
        if not obj.base_cost:
            return "—"
        margin = float(obj.price) - float(obj.base_cost)
        color = "#16a34a" if margin > 0 else "#dc2626"
        return format_html('<span style="color:{}">{}</span>', color, f"{margin:.2f}")

    @admin.display(description=_("Sync"))
    def sync_badge(self, obj):
        colors = {"synced": "#16a34a", "updated": "#2563eb", "draft": "#64748b",
                  "error": "#dc2626", "not_synced": "#94a3b8"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>',
            colors.get(obj.printify_sync_status, "#94a3b8"), obj.get_printify_sync_status_display())

    @admin.action(description=_("Resync selected products from Printify"))
    def resync_from_printify(self, request, queryset):
        from printify_integration.services import resync_product

        ok = err = 0
        for product in queryset:
            log = resync_product(product)
            if log.status == "ok":
                ok += 1
            else:
                err += 1
        self.message_user(request, _("Resynced %(ok)d product(s), %(err)d error(s).") % {
            "ok": ok, "err": err})


@admin.register(Variation)
class VariationAdmin(admin.ModelAdmin):
    list_display = ("product", "variation_category", "variation_value", "is_active",
                    "production_cost", "printify_variant_id")
    list_editable = ("is_active",)
    list_filter = ("variation_category", "is_active")
    search_fields = ("product__product_name", "variation_value")


@admin.register(ReviewRating)
class ReviewRatingAdmin(admin.ModelAdmin):
    list_display = ("subject", "product", "user", "rating", "status", "created_at")
    list_filter = ("status", "rating", "created_at")
    list_editable = ("status",)
    search_fields = ("subject", "review", "product__product_name", "user__email")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        queryset.update(status=True)

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        queryset.update(status=False)


@admin.register(ProductFAQ)
class ProductFAQAdmin(admin.ModelAdmin):
    list_display = ("question", "product", "category", "order", "is_active")
    list_filter = ("is_active", "category")
    list_editable = ("order", "is_active")
    search_fields = ("question", "answer")
    raw_id_fields = ("product",)
    fieldsets = (
        (None, {"fields": ("product", "category", "order", "is_active")}),
        ("English", {"fields": ("question", "answer")}),
        ("Italiano", {"fields": ("question_it", "answer_it")}),
        ("Français", {"fields": ("question_fr", "answer_fr")}),
    )


@admin.register(GeneralFAQ)
class GeneralFAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "order", "is_active")
    list_filter = ("category", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("question", "answer")
    fieldsets = (
        (None, {"fields": ("category", "order", "is_active")}),
        ("English", {"fields": ("question", "answer")}),
        ("Italiano", {"fields": ("question_it", "answer_it")}),
        ("Français", {"fields": ("question_fr", "answer_fr")}),
    )


admin.site.register(ProductImage)
