"""Real recommendation logic: curated relations first, then catalog signals
(category, recently-viewed, wishlist), with a controlled newest-product fallback.
Never returns the current product, inactive products or duplicates."""
from .models import ProductRelation


def _dedupe(products, exclude_ids):
    seen, out = set(exclude_ids), []
    for p in products:
        if p.id not in seen and p.is_available:
            seen.add(p.id)
            out.append(p)
    return out


def recommend_for_product(product, limit=4):
    """Recommendations for a PDP: curated (related/best_match/alternative) → same
    category → newest fallback."""
    from store.models import Product
    exclude = {product.id}
    curated = [r.to_product for r in ProductRelation.objects.filter(
        from_product=product, is_active=True,
        relation_type__in=[ProductRelation.RELATED, ProductRelation.BEST_MATCH,
                           ProductRelation.ALTERNATIVE]).select_related("to_product")]
    result = _dedupe(curated, exclude)
    if len(result) < limit:
        # Same category, ranked by PRICE PROXIMITY to the current product (closest
        # price point first) then newest — a real, explainable signal, not random.
        base_price = float(product.price or 0)
        same_cat = list(Product.objects.filter(is_available=True, category=product.category)
                        .exclude(id=product.id))
        same_cat.sort(key=lambda p: (abs(float(p.price or 0) - base_price), -p.id))
        result = _dedupe(result + same_cat, exclude)
    if len(result) < limit:
        newest = Product.objects.filter(is_available=True).exclude(id=product.id)\
            .order_by("-created_date")
        result = _dedupe(result + list(newest), exclude)
    return result[:limit]


def complete_the_look(product, limit=6):
    """Curated 'complete the look' products for a PDP (no fallback — editorial only)."""
    rels = ProductRelation.objects.filter(
        from_product=product, is_active=True,
        relation_type=ProductRelation.COMPLETE_LOOK).select_related("to_product")
    return _dedupe([r.to_product for r in rels], {product.id})[:limit]


def outfits_for_product(product, limit=3):
    """Active outfits anchored to a product OR containing it."""
    from .models import Outfit
    from django.db.models import Q
    qs = Outfit.objects.filter(is_active=True).filter(
        Q(anchor_product=product) | Q(products=product)).distinct()
    return list(qs[:limit])


def recommend_from_context(request, limit=4, exclude_ids=None):
    """Recommendations for cart / no-results / saved items, from the categories the
    shopper has shown interest in (recently viewed + wishlist), newest first."""
    from store.models import Product
    exclude = set(exclude_ids or [])
    cat_ids = set()
    try:
        from storefront.recently import get_recently_viewed
        for p in get_recently_viewed(request, limit=8):
            cat_ids.add(p.category_id)
            exclude.add(p.id)
    except Exception:
        pass
    try:
        from wishlist.services import items as wishlist_items
        for it in wishlist_items(request)[:8]:
            cat_ids.add(it.product.category_id)
    except Exception:
        pass
    qs = Product.objects.filter(is_available=True)
    if cat_ids:
        qs = qs.filter(category_id__in=cat_ids)
    result = _dedupe(list(qs.order_by("-created_date")[:limit * 3]), exclude)
    if len(result) < limit:
        newest = Product.objects.filter(is_available=True).order_by("-created_date")
        result = _dedupe(result + list(newest), exclude)
    return result[:limit]
