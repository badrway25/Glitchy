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


def saved_items(request):
    return render(request, "wishlist/saved_items.html", {
        "wishlist_items": services.items(request, saved_for_later=False),
        "saved_for_later": services.items(request, saved_for_later=True),
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
