"""Staff-only Printify operations dashboard (no PII, no secrets, no order push)."""
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.shortcuts import render


def _mask_id(value):
    v = str(value or "")
    return (v[:4] + "…" + v[-3:]) if len(v) > 8 else (v or "—")


@staff_member_required
def printify_dashboard(request):
    from django.conf import settings
    from store.models import Product, Variation, ProductImage

    products = list(Product.objects.all().prefetch_related("gallery", "variation_set"))
    synced = [p for p in products if p.printify_blueprint_id]
    variations = Variation.objects.all()
    images = ProductImage.objects.all()

    # --- Overview KPIs ---
    overview = {
        "shop_id": _mask_id(getattr(settings, "PRINTIFY_SHOP_ID", "")),
        "products_total": len(products),
        "products_synced": len(synced),
        "products_unsynced": len(products) - len(synced),
        "variants_total": variations.count(),
        "variants_with_cost": variations.filter(production_cost__gt=0).count(),
        "variants_disabled": variations.filter(printify_is_enabled=False).count(),
        "images_total": images.count(),
        "images_with_meta": images.exclude(printify_position="").count(),
        "push_enabled": getattr(settings, "PRINTIFY_PUSH_ENABLED", False),
        "shipping_source": "printify" if getattr(settings, "SHIPPING_USE_PRINTIFY", False) else "fallback",
    }

    # --- Data quality buckets + per-product rows ---
    rows, buckets = [], {"high": 0, "mid": 0, "low": 0}
    score_sum = 0
    for p in products:
        dq = p.data_quality()
        sc = dq["score"]
        score_sum += sc
        buckets["high" if sc >= 90 else "mid" if sc >= 60 else "low"] += 1
        vqs = p.variation_set.all()
        vcount = vqs.count()
        vcost = sum(1 for v in vqs if v.production_cost > 0)
        rows.append({
            "id": p.id, "name": p.product_name,
            "pid": _mask_id(p.printify_product_id),
            "blueprint": p.printify_blueprint_title or (p.printify_blueprint_id or "—"),
            "provider": p.printify_provider_name or "—",
            "variants": vcount, "variants_cost": vcost,
            "images": p.gallery.count(),
            "cost_cov": round(100 * vcost / vcount) if vcount else 0,
            "score": sc, "missing": dq["missing"][:4],
            "sync": p.get_printify_sync_status_display(),
            "visible": p.printify_visible,
        })
    rows.sort(key=lambda r: r["score"])
    avg_quality = round(score_sum / len(products)) if products else 0

    # --- Variant table (sample, admin-only cost/margin) ---
    vrows = []
    for v in variations.exclude(printify_sku="").select_related("product")[:40]:
        vrows.append({
            "product": v.product.product_name, "title": v.printify_title or v.variation_value,
            "cat": v.variation_category, "value": v.variation_value,
            "sku": v.printify_sku, "enabled": v.printify_is_enabled,
            "available": v.printify_is_available, "price": v.product.price,
            "cost": v.production_cost, "margin": v.margin(), "grams": v.printify_grams,
        })

    # --- Shipping matrix from the PERSISTED profiles (no live API call) ---
    from printify_integration.models import PrintifyShippingProfile, PrintifyPrintArea
    profiles = PrintifyShippingProfile.objects.all()
    ship_rows = []
    for sp in profiles.order_by("country_code", "blueprint_id")[:24]:
        ship_rows.append({
            "country": sp.country_code, "source": sp.source,
            "first": f"{sp.currency} {sp.first_item_cost:.2f}",
            "additional": f"{sp.currency} {sp.additional_item_cost:.2f}",
            "eta": f"{sp.min_delivery_days}-{sp.max_delivery_days}d",
            "checked": sp.last_checked_at})
    shipping_kpi = {
        "profiles": profiles.count(),
        "countries": profiles.values("country_code").distinct().count(),
        "last_checked": profiles.order_by("-last_checked_at").values_list(
            "last_checked_at", flat=True).first(),
    }

    # --- Print area coverage KPIs ---
    areas = PrintifyPrintArea.objects.all()
    with_area_ids = set(areas.values_list("product_id", flat=True))
    printarea_kpi = {
        "products_with": len(with_area_ids),
        "products_without": len([p for p in synced if p.id not in with_area_ids]),
        "placeholders": areas.count(),
        "missing_print_file": areas.filter(has_print_file=False).count(),
    }
    area_rows = [{"product": a.product.product_name, "position": a.position,
                  "placeholders": a.placeholder_count, "has_file": a.has_print_file,
                  "variants": a.variant_count} for a in areas.select_related("product")[:20]]

    ctx = {
        "title": "Printify dashboard",
        "overview": overview, "buckets": buckets, "avg_quality": avg_quality,
        "rows": rows, "vrows": vrows, "ship_rows": ship_rows,
        "shipping_kpi": shipping_kpi, "printarea_kpi": printarea_kpi, "area_rows": area_rows,
    }
    return render(request, "admin/printify_dashboard.html", ctx)
