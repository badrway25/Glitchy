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

    # --- Shipping matrix (live only on explicit request, else fallback) ---
    ship_rows, ship_live = [], False
    sample = next((p for p in synced if p.printify_blueprint_id and p.printify_provider_id), None)
    if sample:
        from shipping.services import quote_for_cart, fallback_quote
        from django.test import override_settings

        class _CI:
            def __init__(s, p): s.product = p; s.quantity = 1
        cart = [_CI(sample)]
        check_live = request.GET.get("check_shipping") == "1"
        for cc in ["BE", "IT", "FR", "US", "MA"]:
            try:
                if check_live:
                    with override_settings(SHIPPING_USE_PRINTIFY=True):
                        q = quote_for_cart(cc, cart, subtotal=sample.price)
                    ship_live = True
                else:
                    q = fallback_quote(cc, 1, sample.price)
                ship_rows.append({
                    "country": cc, "source": q.source,
                    "cost": f"{q.currency} {q.cost:.2f}" if q.available else "n/a",
                    "eta": f"{q.min_days}-{q.max_days}d" if q.available else "—"})
            except Exception as e:
                ship_rows.append({"country": cc, "source": "error",
                                  "cost": type(e).__name__, "eta": "—"})

    ctx = {
        "title": "Printify dashboard",
        "overview": overview, "buckets": buckets, "avg_quality": avg_quality,
        "rows": rows, "vrows": vrows, "ship_rows": ship_rows, "ship_live": ship_live,
    }
    return render(request, "admin/printify_dashboard.html", ctx)
