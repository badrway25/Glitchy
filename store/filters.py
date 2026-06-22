"""Advanced shop filtering: parse & validate URL params into a real queryset,
plus facet options (only those that actually have products) and active-filter state
for chips. Pure data — no fake/empty options, all params sanitised."""
from datetime import timedelta

from django.db.models import Avg, Count, F, Max, Min, Q
from django.utils import timezone

# sort key -> (orm order_by, label key)
SORT_OPTIONS = ["newest", "price_asc", "price_desc", "rating", "name_asc", "name_desc"]
_NEW_DAYS = 14
_BOOL = {"1", "true", "on", "yes"}


def _int(val, default=None, lo=None, hi=None):
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


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


def apply_filters(request, base_qs):
    """Return (queryset, active_filters, sort). `base_qs` is already category-scoped."""
    GET = request.GET
    qs = base_qs
    active = {}

    colors = _list(GET, "color")
    if colors:
        cq = Q()
        for c in colors:
            cq |= Q(variation__variation_value__iexact=c)
        qs = qs.filter(cq, variation__variation_category="color", variation__is_active=True)
        active["color"] = colors

    sizes = _list(GET, "size")
    if sizes:
        sq = Q()
        for s in sizes:
            sq |= Q(variation__variation_value__iexact=s)
        qs = qs.filter(sq, variation__variation_category="size", variation__is_active=True)
        active["size"] = sizes

    min_price = _int(GET.get("min_price"), lo=0, hi=1_000_000)
    max_price = _int(GET.get("max_price"), lo=0, hi=1_000_000)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
        active["min_price"] = min_price
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
        active["max_price"] = max_price

    rating = _int(GET.get("rating"), lo=1, hi=5)
    if rating:
        qs = qs.annotate(_ar=Avg("reviewrating__rating",
                                 filter=Q(reviewrating__status=True))).filter(_ar__gte=rating)
        active["rating"] = rating

    if (GET.get("sale") or "").lower() in _BOOL:
        qs = qs.filter(compare_at_price__isnull=False, compare_at_price__gt=F("price"))
        active["sale"] = True

    if (GET.get("new") or "").lower() in _BOOL:
        qs = qs.filter(created_date__gte=timezone.now() - timedelta(days=_NEW_DAYS))
        active["new"] = True

    if (GET.get("in_stock") or "").lower() in _BOOL:
        qs = qs.filter(stock__gt=0)
        active["in_stock"] = True

    coll = (GET.get("collection") or "").strip()[:140]
    if coll:
        qs = qs.filter(collections__slug=coll, collections__is_active=True)
        active["collection"] = coll

    keyword = (GET.get("keyword") or "").strip()[:60]
    if keyword:
        qs = qs.filter(Q(product_name__icontains=keyword) | Q(description__icontains=keyword))
        active["keyword"] = keyword

    sort = GET.get("sort", "")
    if sort == "rating":
        qs = qs.annotate(_avg=Avg("reviewrating__rating", filter=Q(reviewrating__status=True)))\
               .order_by(F("_avg").desc(nulls_last=True), "-created_date")
    elif sort == "price_asc":
        qs = qs.order_by("price")
    elif sort == "price_desc":
        qs = qs.order_by("-price")
    elif sort == "name_asc":
        qs = qs.order_by("product_name")
    elif sort == "name_desc":
        qs = qs.order_by("-product_name")
    else:
        qs = qs.order_by("-created_date")

    return qs.distinct(), active, sort


def build_facets(base_qs):
    """Available filter options (ONLY those with products) + counts, from the
    category-scoped base queryset (before color/size filters)."""
    from store.models import Variation
    pids = list(base_qs.values_list("id", flat=True))
    if not pids:
        return {"colors": [], "sizes": [], "price": {"lo": 0, "hi": 0},
                "sale_count": 0, "new_count": 0, "instock_count": 0}

    def _variation_facet(cat):
        # group case-insensitively (DB may store "Blu"/"blue", "M"/"m") and lowercase
        # the value so the form, the active state and the filter all agree.
        counts = {}
        rows = (Variation.objects.filter(product_id__in=pids, variation_category=cat, is_active=True)
                .values("variation_value").annotate(n=Count("product_id", distinct=True)))
        for r in rows:
            v = (r["variation_value"] or "").strip().lower()
            if v:
                counts[v] = counts.get(v, 0) + r["n"]
        return [{"value": v, "count": counts[v]} for v in sorted(counts)]

    pr = base_qs.aggregate(lo=Min("price"), hi=Max("price"))
    cutoff = timezone.now() - timedelta(days=_NEW_DAYS)
    return {
        "colors": _variation_facet("color"),
        "sizes": _variation_facet("size"),
        "price": {"lo": pr["lo"] or 0, "hi": pr["hi"] or 0},
        "sale_count": base_qs.filter(compare_at_price__isnull=False,
                                     compare_at_price__gt=F("price")).count(),
        "new_count": base_qs.filter(created_date__gte=cutoff).count(),
        "instock_count": base_qs.filter(stock__gt=0).count(),
    }


def active_chips(active, lang="en"):
    """Flatten active filters into chip descriptors for the template: each chip
    carries the param + value to remove it."""
    chips = []
    for c in active.get("color", []):
        chips.append({"param": "color", "value": c, "label": c.title()})
    for s in active.get("size", []):
        chips.append({"param": "size", "value": s, "label": s.upper()})
    if "min_price" in active:
        chips.append({"param": "min_price", "value": active["min_price"], "label": f"≥ {active['min_price']}"})
    if "max_price" in active:
        chips.append({"param": "max_price", "value": active["max_price"], "label": f"≤ {active['max_price']}"})
    if "rating" in active:
        chips.append({"param": "rating", "value": active["rating"], "label": f"{active['rating']}★+"})
    if active.get("sale"):
        chips.append({"param": "sale", "value": "1", "label": "Sale"})
    if active.get("new"):
        chips.append({"param": "new", "value": "1", "label": "New"})
    if active.get("in_stock"):
        chips.append({"param": "in_stock", "value": "1", "label": "In stock"})
    if "collection" in active:
        chips.append({"param": "collection", "value": active["collection"],
                      "label": active["collection"].replace("-", " ").title()})
    if "keyword" in active:
        chips.append({"param": "keyword", "value": active["keyword"], "label": f'“{active["keyword"]}”'})
    return chips
