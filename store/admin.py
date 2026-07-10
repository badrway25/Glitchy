from django.contrib import admin, messages
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

from .models import (GeneralFAQ, Product, ProductColorImage, ProductColorImageMapRun,
                     ProductDescriptionTranslation, ProductFAQ, ProductImage,
                     ReviewRating, Variation)


def _is_superadmin(user):
    """Same gate as the other control centers: custom is_superadmin OR is_superuser."""
    return bool(getattr(user, "is_superadmin", False) or
                getattr(user, "is_superuser", False))


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
    actions = ["resync_from_printify", "rebuild_color_maps", "dry_run_color_maps",
               "openai_enrich_color_maps", "audit_data_quality",
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

    def _runner_action(self, request, queryset, *, apply, use_openai=False):
        """Shared body for the changelist mapping actions — one runner, one report."""
        from django.urls import reverse
        from printify_integration.map_runner import run_color_image_mapping
        from store.models import ProductColorImageMapRun
        result = run_color_image_mapping(
            products=queryset, apply=apply, source="live",
            use_openai=use_openai, max_ai_calls=20,
            requested_by=str(request.user)[:150])
        # persist the exact selection so the result page's Apply re-runs THIS
        # scope (ids), never a defaulted-to-everything one
        run = ProductColorImageMapRun.objects.get(pk=result["run_id"])
        run.safe_summary_json["params"] = {
            "scope": "ids",
            "ids": ",".join(str(pk) for pk in queryset.values_list("pk", flat=True)),
            "source": "live", "use_openai": "1" if use_openai else "",
            "max_ai_calls": "20", "product_id": "",
        }
        run.save(update_fields=["safe_summary_json"])
        url = reverse("admin:store_colormap_run_result", args=[result["run_id"]])
        self.message_user(request, format_html(
            '{} — <a href="{}">{}</a>',
            _("Colour mapping %(mode)s: %(r)d resolved, %(u)d unresolved "
              "across %(p)d product(s).") % {
                "mode": _("applied") if apply else _("dry-run"),
                "r": result["colors_resolved"], "u": result["colors_unresolved"],
                "p": result["products_scanned"]},
            url, _("Mapping results")))

    @admin.action(description=_("Dry-run colour-image mapping (selected)"))
    def dry_run_color_maps(self, request, queryset):
        self._runner_action(request, queryset, apply=False)

    @admin.action(description=_("OpenAI enrich unresolved mappings (selected)"))
    def openai_enrich_color_maps(self, request, queryset):
        if not _is_superadmin(request.user):
            self.message_user(request, _("Superadmin only."), level=messages.ERROR)
            return
        self._runner_action(request, queryset, apply=True, use_openai=True)

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


@admin.register(ProductColorImageMapRun)
class ProductColorImageMapRunAdmin(BaseModelAdmin):
    """Run history + the "Variant image mapping" operations pages (dashboard,
    dry-run preview, confirm-apply, results). Everything goes through the shared
    runner (printify_integration/map_runner.py) — the same engine as the CLI.
    Dry-run is the default; Apply and the OpenAI stage are superadmin-only."""

    list_display = ("id", "created_at", "created_by", "mode", "source",
                    "status_badge", "products_scanned", "colors_resolved",
                    "colors_unresolved", "openai_calls_used", "duration_ms",
                    "result_link")
    list_filter = ("mode", "status", "use_openai")
    readonly_fields = [f.name for f in ProductColorImageMapRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False    # run history is an audit trail — never hand-deletable

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        colors = {"succeeded": "#16a34a", "partial": "#d97706",
                  "failed": "#dc2626", "running": "#64748b"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;'
            'font-size:11px;">{}</span>',
            colors.get(obj.status, "#94a3b8"), obj.get_status_display())

    @admin.display(description="")
    def result_link(self, obj):
        from django.urls import reverse
        return format_html('<a href="{}">{}</a>',
                           reverse("admin:store_colormap_run_result", args=[obj.pk]),
                           _("Mapping results"))

    # ---- operations pages ----------------------------------------------------
    def get_urls(self):
        from django.urls import path
        return [
            path("mapping/", self.admin_site.admin_view(self.dashboard_view),
                 name="store_colormap_dashboard"),
            path("mapping/preview/", self.admin_site.admin_view(self.preview_view),
                 name="store_colormap_preview"),
            path("mapping/apply/", self.admin_site.admin_view(self.apply_view),
                 name="store_colormap_apply"),
            path("mapping/run/<int:run_id>/",
                 self.admin_site.admin_view(self.result_view),
                 name="store_colormap_run_result"),
        ] + super().get_urls()

    @staticmethod
    def _scope_queryset(params):
        qs = (Product.objects.filter(variation__variation_category="color")
              .distinct().order_by("id"))
        scope = params.get("scope") or "all"
        if scope == "printify":
            qs = qs.exclude(printify_product_id__isnull=True) \
                   .exclude(printify_product_id="")
        elif scope == "product":
            try:
                qs = qs.filter(id=int(params.get("product_id") or 0))
            except (TypeError, ValueError):
                qs = qs.none()
        elif scope == "ids":
            ids = [int(i) for i in str(params.get("ids") or "").split(",")
                   if i.strip().isdecimal()]
            qs = qs.filter(id__in=ids)
        return qs, scope == "unresolved"

    @staticmethod
    def _run_params(request):
        return {
            "scope": request.POST.get("scope") or "all",
            "product_id": request.POST.get("product_id") or "",
            "ids": request.POST.get("ids") or "",
            "source": "live" if request.POST.get("source") == "live" else "db",
            "use_openai": "1" if request.POST.get("use_openai") else "",
            "max_ai_calls": request.POST.get("max_ai_calls") or "20",
        }

    def _openai_available(self):
        try:
            from assistant.providers import OpenAIProvider
            return OpenAIProvider().available()
        except Exception:
            return False

    def dashboard_view(self, request):
        from django.shortcuts import render
        from django.urls import reverse
        resolved = ProductColorImage.objects.exclude(image_ids="").count()
        unresolved = (ProductColorImage.objects.filter(image_ids="")
                      .exclude(source=ProductColorImage.SOURCE_MANUAL).count())
        manual = ProductColorImage.objects.filter(
            source=ProductColorImage.SOURCE_MANUAL).count()
        last = ProductColorImageMapRun.objects.first()
        cards = [
            {"label": _("Resolved colours"), "value": resolved, "color": "#16a34a"},
            {"label": _("Unresolved colours"), "value": unresolved,
             "color": "#dc2626" if unresolved else "#16a34a"},
            {"label": _("Manual pins preserved"), "value": manual, "color": "#0f766e"},
            {"label": _("Products scanned"),
             "value": last.products_scanned if last else "—",
             "hint": _("last run")},
            {"label": "OpenAI", "value": last.openai_calls_used if last else "—",
             "hint": _("calls, last run"), "color": "#7c3aed"},
            {"label": _("Last run"),
             "value": last.created_at.strftime("%Y-%m-%d %H:%M") if last else "—",
             "hint": last.get_status_display() if last else ""},
        ]
        context = dict(
            self.admin_site.each_context(request),
            stat_cards=cards,
            recent_runs=ProductColorImageMapRun.objects.all()[:10],
            preview_url=reverse("admin:store_colormap_preview"),
            openai_available=self._openai_available(),
        )
        return render(request, "admin/store/mapping_dashboard.html", context)

    def preview_view(self, request):
        from django.http import HttpResponseNotAllowed
        from django.shortcuts import redirect
        from printify_integration.map_runner import run_color_image_mapping
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        params = self._run_params(request)
        qs, only_unresolved = self._scope_queryset(params)
        result = run_color_image_mapping(
            products=qs, apply=False, source=params["source"],
            use_openai=False, only_unresolved=only_unresolved,
            requested_by=str(request.user)[:150])
        run = ProductColorImageMapRun.objects.get(pk=result["run_id"])
        run.safe_summary_json["params"] = params
        run.save(update_fields=["safe_summary_json"])
        return redirect("admin:store_colormap_run_result", run_id=run.pk)

    def apply_view(self, request):
        from django.http import HttpResponseForbidden, HttpResponseNotAllowed
        from django.shortcuts import redirect
        from printify_integration.map_runner import run_color_image_mapping
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not _is_superadmin(request.user):
            return HttpResponseForbidden("Superadmin only.")
        if not request.POST.get("confirm"):
            self.message_user(request, _("Please confirm before applying."),
                              level=messages.WARNING)
            return redirect("admin:store_colormap_dashboard")
        params = self._run_params(request)
        qs, only_unresolved = self._scope_queryset(params)
        try:
            max_ai = max(1, min(200, int(params["max_ai_calls"])))
        except (TypeError, ValueError):
            max_ai = 20
        result = run_color_image_mapping(
            products=qs, apply=True, source=params["source"],
            use_openai=bool(params["use_openai"]), max_ai_calls=max_ai,
            only_unresolved=only_unresolved,
            requested_by=str(request.user)[:150])
        run = ProductColorImageMapRun.objects.get(pk=result["run_id"])
        run.safe_summary_json["params"] = params
        run.save(update_fields=["safe_summary_json"])
        self.message_user(request, _("Mapping applied: %(r)d colours resolved, "
                                     "%(u)d unresolved.") % {
            "r": result["colors_resolved"], "u": result["colors_unresolved"]})
        return redirect("admin:store_colormap_run_result", run_id=run.pk)

    def result_view(self, request, run_id):
        import json as jsonlib
        from django.shortcuts import get_object_or_404, render
        run = get_object_or_404(ProductColorImageMapRun, pk=run_id)
        summary = run.safe_summary_json or {}
        rows = summary.get("rows") or []
        products = Product.objects.in_bulk({r["product_id"] for r in rows})
        for row in rows:
            product = products.get(row["product_id"])
            try:
                row["product_url"] = product.get_url() if product else ""
            except Exception:
                row["product_url"] = ""
        run.use_openai_requested = bool((summary.get("params") or {}).get("use_openai"))
        cards = [
            {"label": _("Products scanned"), "value": run.products_scanned},
            {"label": _("Products changed"), "value": run.products_changed},
            {"label": _("Resolved colours"), "value": run.colors_resolved,
             "color": "#16a34a"},
            {"label": _("Unresolved colours"), "value": run.colors_unresolved,
             "color": "#dc2626" if run.colors_unresolved else "#16a34a"},
            {"label": _("Manual pins preserved"), "value": run.manual_preserved,
             "color": "#0f766e"},
            {"label": "OpenAI", "value": run.openai_calls_used, "color": "#7c3aed"},
        ]
        apply_params = summary.get("params") or {}
        context = dict(
            self.admin_site.each_context(request),
            run=run, rows=rows, warnings=summary.get("warnings") or [],
            stat_cards=cards,
            # no stored params (e.g. CLI runs) -> no Apply button: re-running with
            # a defaulted scope would silently expand a selection to the whole catalog
            can_apply=_is_superadmin(request.user) and bool(apply_params),
            apply_params=apply_params,
            diagnostics_json=jsonlib.dumps(summary, indent=1)[:20000],
        )
        return render(request, "admin/store/mapping_result.html", context)


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
