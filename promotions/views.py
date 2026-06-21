"""Coupon apply/remove from the cart."""
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services


def cart_subtotal(request):
    """Sum the current cart (price * quantity) for the active user/guest."""
    from carts.models import Cart, CartItem
    from carts.views import _cart_id
    if request.user.is_authenticated:
        qs = CartItem.objects.filter(user=request.user, is_active=True)
    else:
        cart = Cart.objects.filter(cart_id=_cart_id(request)).first()
        qs = CartItem.objects.filter(cart=cart, is_active=True) if cart else CartItem.objects.none()
    total = Decimal("0")
    for it in qs.select_related("product"):
        total += Decimal(str(it.product.price)) * it.quantity
    return total


def _track(request, name, meta=None):
    try:
        from storefront.models import AnalyticsEvent
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(name=name, path=request.path[:255],
                                      session_key=request.session.session_key or "", meta=meta or {})
    except Exception:
        pass


@require_POST
def apply_coupon(request):
    code = (request.POST.get("code") or "")[:32]
    result = services.apply(request, code, cart_subtotal(request))
    if result["ok"]:
        messages.success(request, result["message"])
        _track(request, "coupon_apply", {"code": result.get("code", "")})
    else:
        messages.error(request, result["message"])
        _track(request, "coupon_fail", {"code": code.strip().upper()[:32]})
    return redirect("cart")


@require_POST
def remove_coupon(request):
    services.clear(request)
    messages.info(request, _("Coupon removed."))
    return redirect("cart")
