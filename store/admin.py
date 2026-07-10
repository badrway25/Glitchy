from django.contrib import admin
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

try:                                        # premium admin styling
    from unfold.admin import ModelAdmin as BaseModelAdmin
    from unfold.admin import TabularInline as BaseTabularInline
except Exception:                           # graceful fallback if Unfold is absent
    from django.contrib.admin import ModelAdmin as BaseModelAdmin
    from django.contrib.admin import TabularInline as BaseTabularInline

from .models import (GeneralFAQ, Product, ProductColorImage, ProductDescriptionTranslation,
                     ProductFAQ, ProductImage, ReviewRating, Variation)


# --- Catalog-health filters (drive the dashboard quick links) ---------------
class MissingImageFilter(admin.SimpleListFilter):
    title = _("image")
    parameter_name = "missing_image"

    def lookups(self, request, model_admin):
        return [("1", _("Missing image"))]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.annotate(_g=Count("gallery")).filter(
                _g=0).filter(Q(images="") | Q(images__isnull=True))
        return queryset


class MissingPriceFilter(admin.SimpleListFilter):
    title = _("price")
    parameter_name = "missing_price"

    def lookups(self, request, model_admin):
        return [("1", _("Missing / zero price"))]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(Q(price__isnull=True) | Q(price__lte=0))
        return queryset


class PrintifyFilter(admin.SimpleListFilter):
    title = _("Printify")
    parameter_name = "printify"

    def lookups(self, request, model_admin):
        return [("1", _("Printify products")), ("0", _("Local only"))]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.exclude(printify_product_id__isnull=True).exclude(printify_product_id="")
        if self.value() == "0":
            return queryset.filter(Q(printify_product_id__isnull=True) | Q(printify_product_id=""))
        return queryset


class StaleSyncFilter(admin.SimpleListFilter):
    title = _("sync freshness")
    parameter_name = "stale_sync"

    def lookups(self, request, model_admin):
        return [("1", _("Stale Printify sync"))]

    def queryset(self, request, queryset):
        if self.value() == "1":
            from django.conf import settings
            cutoff = timezone.now() - timezone.timedelta(
                minutes=getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360))
            return queryset.filter(printify_product_id__isnull=False, printify_synced_at__lt=cutoff)
        return queryset


class ProductImageInline(BaseTabularInline):
    model = ProductImage
    extra = 0


class VariationInline(admin.TabularInline):
    model = Variation
    extra = 0
    fields = ("variation_category", "variation_value", "is_active",
              "printify_variant_id", "production_cost")


class DescriptionTranslationInline(admin.TabularInline):
    model = ProductDescriptionTranslation
    extra = 0
    fields = ("language", "status", "freshness", "translated_at", "translated_text", "error_code")
    readonly_fields = ("freshness", "translated_at")

    @admin.display(description=_("Up to date"), boolean=True)
    def freshness(self, obj):
        return obj.is_fresh() if obj and obj.pk else False


class ColorImageMapInline(admin.TabularInline):
    """Read-only view of the persisted colour→image mapping (rebuilt by sync or the
    'Rebuild colour-image maps' action; edited only via its own admin for manual pins)."""
    model = ProductColorImage
    extra = 0
    can_delete = False
    fields = ("color_value", "source", "confidence", "image_count", "detail", "built_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Images"))
    def image_count(self, obj):
        return len(obj.image_id_list()) if obj and obj.pk else 0


@admin.register(Product)
class ProductAdmin(BaseModelAdmin):
    list_display = ("thumb", "product_name", "price", "margin_hint", "quality_score",
                    "img_count", "variant_count", "stock", "category", "sync_badge",
                    "is_available", "is_bestseller")
    list_display_links = ("thumb", "product_name")
    list_filter = ("category", "is_available", "is_bestseller", "is_featured",
                   "printify_sync_status", "printify_visible",
                   PrintifyFilter, MissingImageFilter, MissingPriceFilter, StaleSyncFilter)
    list_editable = ("is_available", "is_bestseller")
    list_select_related = ("category",)
    search_fields = ("product_name", "sku", "printify_product_id")
    prepopulated_fields = {"slug": ("product_name",)}
    readonly_fields = ("printify_synced_at", "printify_sync_error", "printify_panel",
                       "big_preview", "printify_description_raw")
    inlines = [ProductImageInline, VariationInline, DescriptionTranslationInline,
               ColorImageMapInline]
    actions = ["resync_from_printify", "rebuild_color_maps", "audit_data_quality",
               "translate_missing_descriptions",
               "bulk_activate", "bulk_deactivate", "bulk_mark_stale"]

    def get_queryset(self, request):
        # annotate counts once -> no N+1 for img_count / variant_count in the list
        return (super().get_queryset(request)
                .annotate(_img_n=Count("gallery", distinct=True),
                          _var_n=Count("variation", distinct=True)))

    @admin.display(description="")
    def thumb(self, obj):
        src = ""
        first = obj.gallery.first() if hasattr(obj, "gallery") else None
        if first and getattr(first, "image", None):
            try:
                src = first.image.url
            except Exception:
                src = ""
        if not src and obj.images:
            try:
                src = obj.images.url
            except Exception:
                src = ""
        if not src:
            return mark_safe('<div style="width:44px;height:44px;border-radius:8px;'
                             'background:rgba(120,120,120,.15);display:flex;align-items:center;'
                             'justify-content:center;font-size:10px;opacity:.6;">&mdash;</div>')
        return format_html('<img src="{}" style="width:44px;height:44px;object-fit:cover;'
                           'border-radius:8px;" loading="lazy">', src)

    @admin.display(description=_("Full preview"))
    def big_preview(self, obj):
        imgs = list(obj.gallery.all()[:6]) if hasattr(obj, "gallery") else []
        srcs = []
        for im in imgs:
            try:
                srcs.append(im.image.url)
            except Exception:
                pass
        if not srcs and obj.images:
            try:
                srcs = [obj.images.url]
            except Exception:
                srcs = []
        if not srcs:
            return _("No images")
        from django.utils.html import escape
        inner = "".join(
            '<img src="%s" style="width:110px;height:110px;object-fit:cover;border-radius:10px;">' % escape(s)
            for s in srcs)
        return mark_safe("<div style='display:flex;gap:8px;flex-wrap:wrap;'>%s</div>" % inner)

    @admin.display(description=_("Imgs"), ordering="_img_n")
    def img_count(self, obj):
        n = getattr(obj, "_img_n", None)
        n = n if n is not None else (obj.gallery.count() if hasattr(obj, "gallery") else 0)
        color = "#dc2626" if not n else "inherit"
        return format_html('<span style="color:{}">{}</span>', color, n)

    @admin.display(description=_("Vars"), ordering="_var_n")
    def variant_count(self, obj):
        n = getattr(obj, "_var_n", None)
        n = n if n is not None else obj.variation_set.count()
        return n

    @admin.action(description=_("Activate selected"))
    def bulk_activate(self, request, queryset):
        n = queryset.update(is_available=True)
        self.message_user(request, _("Activated %(n)d product(s).") % {"n": n})

    @admin.action(description=_("Deactivate selected"))
    def bulk_deactivate(self, request, queryset):
        n = queryset.update(is_available=False)
        self.message_user(request, _("Deactivated %(n)d product(s).") % {"n": n})

    @admin.action(description=_("Mark Printify sync stale (selected)"))
    def bulk_mark_stale(self, request, queryset):
        old = timezone.now() - timezone.timedelta(days=3650)
        n = queryset.exclude(printify_product_id__isnull=True).exclude(
            printify_product_id="").update(printify_synced_at=old)
        self.message_user(request, _("Marked %(n)d Printify product(s) as stale.") % {"n": n})
    fieldsets = (
        (None, {"fields": ("product_name", "slug", "category", "description")}),
        (_("Pricing & stock"), {"fields": ("price", "compare_at_price", "base_cost",
                                           "stock", "is_available")}),
        (_("Premium content"), {"fields": ("composition", "fit_notes", "care_instructions")}),
        (_("Merchandising"), {"fields": ("is_bestseller", "is_featured", "images", "big_preview")}),
        (_("Printify"), {"fields": ("printify_panel", "printify_product_id",
                                    "printify_blueprint_id", "printify_provider_id", "sku",
                                    "printify_blueprint_title", "printify_provider_name",
                                    "printify_options_summary", "printify_tags",
                                    "printify_visible", "printify_sync_status",
                                    "printify_synced_at", "printify_sync_error")}),
        (_("Printify raw description (reference)"), {
            "classes": ("collapse",),
            "fields": ("printify_description_raw",),
        }),
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

    @admin.action(description=_("Rebuild colour-image maps (selected)"))
    def rebuild_color_maps(self, request, queryset):
        """Deterministic + heuristic rebuild only (no network, no OpenAI) — the
        offline `build_color_image_maps` command covers refetch/AI stages."""
        from printify_integration.variant_images import rebuild_color_image_map

        import logging
        resolved = colors = err = 0
        for product in queryset:
            try:
                summary = rebuild_color_image_map(product)
                colors += summary["colors"]
                resolved += summary["resolved"]
            except Exception as exc:
                err += 1
                logging.getLogger("printify").warning(
                    "admin colour-map rebuild failed for %s: %s",
                    product.slug, exc.__class__.__name__)
        self.message_user(request, _(
            "Colour-image maps rebuilt: %(r)d/%(c)d colours resolved, %(e)d error(s).") % {
            "r": resolved, "c": colors, "e": err})

    @admin.action(description=_("Translate missing descriptions (IT/FR)"))
    def translate_missing_descriptions(self, request, queryset):
        from assistant import translation

        if not translation.translation_available():
            self.message_user(request, _("OpenAI key not configured — no translations made."),
                              level="warning")
            return
        wrote = failed = 0
        for product in queryset:
            for lang in translation.SUPPORTED_TARGET_LANGS:
                res = translation.ensure_product_translation(product, lang, apply=True)
                if res["action"] == "translated":
                    wrote += 1
                elif res["action"] == "failed":
                    failed += 1
        self.message_user(request, _("Translations written: %(w)d, failed: %(f)d.") % {
            "w": wrote, "f": failed})


@admin.register(ProductColorImage)
class ProductColorImageAdmin(BaseModelAdmin):
    """Inspection surface for the colour→image mapping. Rows are normally rebuilt by
    the Printify sync / the Product admin action / `build_color_image_maps`; editing
    here (and setting source=manual) pins a mapping so rebuilds never overwrite it."""
    list_display = ("product", "color_value", "source_badge", "confidence",
                    "image_count", "primary_thumb", "detail", "built_at")
    list_filter = ("source",)
    search_fields = ("product__product_name", "color_value")
    readonly_fields = ("built_at", "primary_thumb")
    raw_id_fields = ("product", "primary_image")
    list_select_related = ("product", "primary_image")

    SOURCE_COLORS = {
        ProductColorImage.SOURCE_DETERMINISTIC: "#16a34a",  # green — exact data
        ProductColorImage.SOURCE_HEURISTIC: "#d97706",      # amber — inferred locally
        ProductColorImage.SOURCE_OPENAI: "#7c3aed",         # violet — AI-classified
        ProductColorImage.SOURCE_MANUAL: "#64748b",         # slate — pinned by admin
    }

    @admin.display(description=_("Source"), ordering="source")
    def source_badge(self, obj):
        if not obj.image_id_list():
            # an empty row means no stage could resolve this colour — saying
            # "Deterministic" there would misread as a confident mapping
            return format_html(
                '<span style="background:#94a3b8;color:#fff;padding:2px 8px;'
                'border-radius:999px;font-size:11px;">{}</span>', _("Unresolved"))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>',
            self.SOURCE_COLORS.get(obj.source, "#94a3b8"), obj.get_source_display())

    @admin.display(description=_("Images"))
    def image_count(self, obj):
        n = len(obj.image_id_list())
        color = "#dc2626" if not n else "inherit"
        return format_html('<span style="color:{}">{}</span>', color, n)

    @admin.display(description=_("Primary"))
    def primary_thumb(self, obj):
        img = obj.primary_image
        url = img.display_url() if img else ""
        if not url:
            return "—"
        return format_html('<img src="{}" style="width:44px;height:44px;object-fit:cover;'
                           'border-radius:8px;" loading="lazy">', url)


@admin.register(ProductDescriptionTranslation)
class ProductDescriptionTranslationAdmin(admin.ModelAdmin):
    list_display = ("product", "language", "status", "is_fresh", "translated_at")
    list_filter = ("language", "status")
    search_fields = ("product__product_name",)
    readonly_fields = ("source_hash", "translated_at")

    @admin.display(boolean=True, description=_("Up to date"))
    def is_fresh(self, obj):
        return obj.is_fresh()


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
