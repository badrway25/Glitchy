"""Wishlist endpoints + the account 'Saved items' page."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services


def _track(request, name, meta=None):
    try:
        from storefront.models import AnalyticsEvent
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(name=name, path=request.path[:255],
                                      session_key=request.session.session_key or "",
                                      meta=meta or {})
    except Exception:
        pass


@require_POST
def toggle(request):
    try:
        pid = int(json.loads(request.body or "{}").get("product_id"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    from store.models import Product
    if not Product.objects.filter(id=pid, is_available=True).exists():
        return JsonResponse({"error": "not_found"}, status=404)
    added = services.toggle(request, pid)
    _track(request, "wishlist_add" if added else "wishlist_remove", {"id": str(pid)})
    return JsonResponse({"in_wishlist": added, "count": services.count(request)})


def _name_of(it):
    return (getattr(getattr(it, "product", None), "product_name", "") or "").lower()


def saved_items(request):
    from django.core.paginator import Paginator
    from . import facets

    q = (request.GET.get("q") or "").strip()[:60]
    active = facets.parse(request)
    sort = active["sort"]

    base_items = list(services.items(request, saved_for_later=False))
    saved_for_later = list(services.items(request, saved_for_later=True))

    # Facet options from ALL saved products (so options stay visible while filtering).
    all_pids = [it.product_id for it in base_items]
    facet_data = facets.build_facets(all_pids)

    # Product-level facets (category/color/size/price/sale/multi) — DB-side, ownership-safe.
    matched = facets.matching_product_ids(all_pids, active)
    items = [it for it in base_items if it.product_id in matched]

    if q:
        ql = q.lower()
        items = [it for it in items if ql in _name_of(it)]
        saved_for_later = [it for it in saved_for_later if ql in _name_of(it)]
    if active.get("recent"):
        cutoff = facets.recent_cutoff()
        items = [it for it in items if getattr(it, "created_at", None) and it.created_at >= cutoff]

    items = facets.sort_items(items, sort)
    saved_for_later = facets.sort_items(saved_for_later, sort)

    chips = facets.active_chips(active)
    has_filters = bool(q or chips or sort != "newest")
    total_matched = len(items)

    paginator = Paginator(items, 12)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "wishlist/saved_items.html", {
        "wishlist_items": page,
        "saved_for_later": saved_for_later,
        "q": q,
        "sort": sort, "sort_options": facets.WISHLIST_SORTS,
        "facets": facet_data, "active": active, "chips": chips,
        "has_query": has_filters, "has_filters": has_filters,
        "result_count": total_matched + len(saved_for_later),
        "total_saved": len(all_pids) + len(saved_for_later),
        "filtered_count": total_matched,
        "querystring": params.urlencode(),
    })


@require_POST
def save_for_later(request):
    """Move an item out of the cart into the wishlist (kept as save-for-later)."""
    try:
        pid = int(request.POST.get("product_id"))
    except (ValueError, TypeError):
        return redirect("cart")
    services.add(request, pid, saved_for_later=True)
    _track(request, "cart_save_for_later", {"id": str(pid)})
    # remove the matching cart item(s)
    try:
        from carts.models import CartItem, Cart
        from carts.views import _cart_id
        if request.user.is_authenticated:
            CartItem.objects.filter(user=request.user, product_id=pid).delete()
        else:
            cart = Cart.objects.filter(cart_id=_cart_id(request)).first()
            if cart:
                CartItem.objects.filter(cart=cart, product_id=pid).delete()
    except Exception:
        pass
    messages.success(request, _("Saved for later."))
    return redirect("cart")
