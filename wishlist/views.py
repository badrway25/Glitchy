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


WISHLIST_SORTS = {
    "newest": "Recently added",
    "name": "Name A–Z",
    "price_low": "Price: low to high",
    "price_high": "Price: high to low",
}


def _wishlist_sort_key(sort):
    def price(it):
        return float(getattr(getattr(it, "product", None), "price", 0) or 0)
    def name(it):
        return (getattr(getattr(it, "product", None), "product_name", "") or "").lower()
    if sort == "name":
        return name, False
    if sort == "price_low":
        return price, False
    if sort == "price_high":
        return price, True
    return (lambda it: getattr(it, "created_at", None) or 0), True  # newest


def saved_items(request):
    q = (request.GET.get("q") or "").strip()[:60]
    sort = (request.GET.get("sort") or "newest").strip()
    if sort not in WISHLIST_SORTS:
        sort = "newest"
    wishlist_items = list(services.items(request, saved_for_later=False))
    saved_for_later = list(services.items(request, saved_for_later=True))
    if q:
        ql = q.lower()

        def _match(it):
            name = (getattr(getattr(it, "product", None), "product_name", "") or "").lower()
            return ql in name
        wishlist_items = [it for it in wishlist_items if _match(it)]
        saved_for_later = [it for it in saved_for_later if _match(it)]
    key, rev = _wishlist_sort_key(sort)
    wishlist_items.sort(key=key, reverse=rev)
    saved_for_later.sort(key=key, reverse=rev)
    return render(request, "wishlist/saved_items.html", {
        "wishlist_items": wishlist_items,
        "saved_for_later": saved_for_later,
        "q": q,
        "has_query": bool(q or sort != "newest"),
        "sort": sort,
        "sort_options": WISHLIST_SORTS,
        "result_count": len(wishlist_items) + len(saved_for_later),
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
