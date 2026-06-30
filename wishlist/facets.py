"""Wishlist facets — Product-level filters over a user's saved items.

Pure data, reusing the store facet conventions (case-insensitive variation grouping,
only options that actually have items). All inputs validated/whitelisted — no field
injection. Filtering runs on a Product queryset scoped to the saved product ids, so it
never leaks another user's data and never triggers an N+1.
"""
from datetime import timedelta

from django.db.models import Count, F, Max, Min, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from store.models import Product, Variation

_BOOL = {"1", "true", "on", "yes"}
_RECENT_DAYS = 14

# sort key -> human label (translated in the template/view)
WISHLIST_SORTS = {
    "newest": "Recently added",
    "name": "Name A–Z",
    "price_low": "Price: low to high",
    "price_high": "Price: high to low",
}


def _list(get, key, limit=12):
    out, seen = [], set()
    for v in get.getlist(key):
        v = (v or "").strip().lower()[:40]
        if v and v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= limit:
            break
    return out


def _int(val, lo=0, hi=1_000_000):
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def parse(request):
    """Validate the wishlist filter params into an `active` dict (no DB hit)."""
    G = request.GET
    active = {}
    cat = (G.get("category") or "").strip()[:140]
    if cat:
        active["category"] = cat
    colors = _list(G, "color")
    if colors:
        active["color"] = colors
    sizes = _list(G, "size")
    if sizes:
        active["size"] = sizes
    mn = _int(G.get("min_price"))
    if mn is not None:
        active["min_price"] = mn
    mx = _int(G.get("max_price"))
    if mx is not None:
        active["max_price"] = mx
    if (G.get("sale") or "").lower() in _BOOL:
        active["sale"] = True
    if (G.get("multi") or "").lower() in _BOOL:
        active["multi"] = True
    if (G.get("recent") or "").lower() in _BOOL:
        active["recent"] = True
    sort = (G.get("sort") or "newest").strip()
    active["sort"] = sort if sort in WISHLIST_SORTS else "newest"
    return active


def matching_product_ids(pids, active):
    """Product-level facets -> the set of product ids that pass (DB-side, no N+1).
    The `recent` facet is NOT applied here (it lives on WishlistItem.created_at)."""
    qs = Product.objects.filter(id__in=pids)
    if active.get("category"):
        qs = qs.filter(category__slug=active["category"])
    if active.get("color"):
        cq = Q()
        for c in active["color"]:
            cq |= Q(variation__variation_value__iexact=c)
        qs = qs.filter(cq, variation__variation_category="color", variation__is_active=True)
    if active.get("size"):
        sq = Q()
        for s in active["size"]:
            sq |= Q(variation__variation_value__iexact=s)
        qs = qs.filter(sq, variation__variation_category="size", variation__is_active=True)
    if "min_price" in active:
        qs = qs.filter(price__gte=active["min_price"])
    if "max_price" in active:
        qs = qs.filter(price__lte=active["max_price"])
    if active.get("sale"):
        qs = qs.filter(compare_at_price__isnull=False, compare_at_price__gt=F("price"))
    if active.get("multi"):
        qs = qs.annotate(_g=Count("gallery")).filter(_g__gt=1)
    return set(qs.values_list("id", flat=True).distinct())


def build_facets(pids):
    """Available options (only those with saved items) + counts."""
    empty = {"categories": [], "colors": [], "sizes": [],
             "price": {"lo": 0, "hi": 0}, "sale_count": 0, "multi_count": 0}
    if not pids:
        return empty
    qs = Product.objects.filter(id__in=pids)

    cats = (qs.exclude(category__isnull=True)
            .values("category__slug", "category__category_name")
            .annotate(n=Count("id", distinct=True)).order_by("-n", "category__category_name"))
    categories = [{"slug": c["category__slug"], "name": c["category__category_name"], "count": c["n"]}
                  for c in cats if c["category__slug"]]

    def vf(cat):
        counts = {}
        rows = (Variation.objects.filter(product_id__in=pids, variation_category=cat, is_active=True)
                .values("variation_value").annotate(n=Count("product_id", distinct=True)))
        for r in rows:
            v = (r["variation_value"] or "").strip().lower()
            if v:
                counts[v] = counts.get(v, 0) + r["n"]
        return [{"value": v, "count": counts[v]} for v in sorted(counts)]

    pr = qs.aggregate(lo=Min("price"), hi=Max("price"))
    return {
        "categories": categories,
        "colors": vf("color"),
        "sizes": vf("size"),
        "price": {"lo": pr["lo"] or 0, "hi": pr["hi"] or 0},
        "sale_count": qs.filter(compare_at_price__isnull=False, compare_at_price__gt=F("price")).count(),
        "multi_count": qs.annotate(_g=Count("gallery")).filter(_g__gt=1).count(),
    }


def recent_cutoff():
    return timezone.now() - timedelta(days=_RECENT_DAYS)


def sort_items(items, sort):
    """Sort the materialised WishlistItem list by the chosen (whitelisted) key."""
    def price(it):
        return float(getattr(getattr(it, "product", None), "price", 0) or 0)
    def name(it):
        return (getattr(getattr(it, "product", None), "product_name", "") or "").lower()
    if sort == "name":
        return sorted(items, key=name)
    if sort == "price_low":
        return sorted(items, key=price)
    if sort == "price_high":
        return sorted(items, key=price, reverse=True)
    return sorted(items, key=lambda it: getattr(it, "created_at", None) or recent_cutoff(), reverse=True)


def active_chips(active):
    """Active facets as removable chip descriptors (label translated in template)."""
    chips = []
    if active.get("category"):
        chips.append({"param": "category", "value": active["category"],
                      "label": active["category"].replace("-", " ").title()})
    for c in active.get("color", []):
        chips.append({"param": "color", "value": c, "label": c.title()})
    for s in active.get("size", []):
        chips.append({"param": "size", "value": s, "label": s.upper()})
    if "min_price" in active:
        chips.append({"param": "min_price", "value": active["min_price"], "label": "≥ %s" % active["min_price"]})
    if "max_price" in active:
        chips.append({"param": "max_price", "value": active["max_price"], "label": "≤ %s" % active["max_price"]})
    if active.get("sale"):
        chips.append({"param": "sale", "value": "1", "label": _("On sale")})
    if active.get("multi"):
        chips.append({"param": "multi", "value": "1", "label": _("Multi-image")})
    if active.get("recent"):
        chips.append({"param": "recent", "value": "1", "label": _("Recently saved")})
    return chips
