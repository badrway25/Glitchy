from django.shortcuts import render, redirect, get_object_or_404
from store.models import Product, Variation
from .models import Cart, CartItem
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required
from accounts.models import Address
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST


def _cart_id(request):
    cart = request.session.session_key
    if not cart:
        cart = request.session.create()
    return cart


def _missing_required_variations(product, matched):
    """Variation categories the product OFFERS (colour/size) that weren't selected.

    Used to reject an under-specified add-to-cart server-side (the PDP modal is the UX
    layer; this is the authoritative guard). The cart qty-stepper re-posts the chosen
    variations, so it never trips this; one-size products offer no colour/size and pass.
    """
    matched_cats = {v.variation_category.lower() for v in matched}
    missing = []
    if product.variation_set.colors().exists() and "color" not in matched_cats:
        missing.append("color")
    if product.variation_set.sizes().exists() and "size" not in matched_cats:
        missing.append("size")
    return missing


def add_cart(request, product_id):
    current_user = request.user
    product = get_object_or_404(Product, id=product_id)

    # =========================
    # AUTH USER
    # =========================
    if current_user.is_authenticated:
        product_variation = []
        if request.method == 'POST':
            for item in request.POST:
                key = item
                value = request.POST[key]
                try:
                    variation = Variation.objects.get(
                        product=product,
                        variation_category__iexact=key,
                        variation_value__iexact=value
                    )
                    product_variation.append(variation)
                except Variation.DoesNotExist:
                    pass

        if request.method == 'POST' and _missing_required_variations(product, product_variation):
            messages.error(request, _("Please choose a colour and size before adding this item to your cart."))
            return redirect(product.get_url())

        is_cart_item_exists = CartItem.objects.filter(product=product, user=current_user).exists()

        if is_cart_item_exists:
            cart_item = CartItem.objects.filter(product=product, user=current_user)
            ex_var_list = []
            id_list = []

            for item in cart_item:
                existing_variation = item.variations.all()
                ex_var_list.append(list(existing_variation))
                id_list.append(item.id)

            if product_variation in ex_var_list:
                index = ex_var_list.index(product_variation)
                item_id = id_list[index]
                item = CartItem.objects.get(product=product, id=item_id)
                item.quantity += 1
                item.save()
                messages.success(request, f"Updated quantity for {product.product_name}.")

            else:
                item = CartItem.objects.create(product=product, quantity=1, user=current_user)
                if len(product_variation) > 0:
                    item.variations.clear()
                    item.variations.add(*product_variation)
                item.save()
                messages.success(request, f"Added {product.product_name} to cart.")
        else:
            cart_item = CartItem.objects.create(
                product=product,
                quantity=1,
                user=current_user,
            )
            if len(product_variation) > 0:
                cart_item.variations.clear()
                cart_item.variations.add(*product_variation)
            cart_item.save()
            messages.success(request, f"Added {product.product_name} to cart.")

        return redirect('cart')

    # =========================
    # GUEST USER
    # =========================
    product_variation = []
    if request.method == 'POST':
        for item in request.POST:
            key = item
            value = request.POST[key]
            try:
                variation = Variation.objects.get(
                    product=product,
                    variation_category__iexact=key,
                    variation_value__iexact=value
                )
                product_variation.append(variation)
            except Variation.DoesNotExist:
                pass

    if request.method == 'POST' and _missing_required_variations(product, product_variation):
        messages.error(request, _("Please choose a colour and size before adding this item to your cart."))
        return redirect(product.get_url())

    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
    except Cart.DoesNotExist:
        cart = Cart.objects.create(cart_id=_cart_id(request))
    cart.save()

    is_cart_item_exists = CartItem.objects.filter(product=product, cart=cart).exists()

    if is_cart_item_exists:
        cart_item = CartItem.objects.filter(product=product, cart=cart)
        ex_var_list = []
        id_list = []

        for item in cart_item:
            existing_variation = item.variations.all()
            ex_var_list.append(list(existing_variation))
            id_list.append(item.id)

        if product_variation in ex_var_list:
            index = ex_var_list.index(product_variation)
            item_id = id_list[index]
            item = CartItem.objects.get(product=product, id=item_id)
            item.quantity += 1
            item.save()
            messages.info(request, "Cart updated.")
        else:
            item = CartItem.objects.create(product=product, quantity=1, cart=cart)
            if len(product_variation) > 0:
                item.variations.clear()
                item.variations.add(*product_variation)
            item.save()
            messages.success(request, "Added to cart.")
    else:
        cart_item = CartItem.objects.create(
            product=product,
            quantity=1,
            cart=cart,
        )
        if len(product_variation) > 0:
            cart_item.variations.clear()
            cart_item.variations.add(*product_variation)
        cart_item.save()
        messages.success(request, "Added to cart.")

    return redirect('cart')


def remove_cart(request, product_id, cart_item_id):
    product = get_object_or_404(Product, id=product_id)

    try:
        if request.user.is_authenticated:
            cart_item = CartItem.objects.get(product=product, user=request.user, id=cart_item_id)
        else:
            cart = Cart.objects.get(cart_id=_cart_id(request))
            cart_item = CartItem.objects.get(product=product, cart=cart, id=cart_item_id)

        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
            messages.success(request, f"Updated quantity for {product.product_name}.")
        else:
            cart_item.delete()
            messages.info(request, f"Removed {product.product_name} from cart.")

    except CartItem.DoesNotExist:
        messages.error(request, "Item not found in cart.")
    except Exception:
        messages.error(request, "Could not update the cart. Please try again.")

    return redirect('cart')


def remove_cart_item(request, product_id, cart_item_id):
    product = get_object_or_404(Product, id=product_id)

    try:
        if request.user.is_authenticated:
            cart_item = CartItem.objects.get(product=product, user=request.user, id=cart_item_id)
        else:
            cart = Cart.objects.get(cart_id=_cart_id(request))
            cart_item = CartItem.objects.get(product=product, cart=cart, id=cart_item_id)

        cart_item.delete()
        messages.info(request, f"Removed {product.product_name} from cart.")

    except CartItem.DoesNotExist:
        messages.error(request, "Item not found in cart.")
    except Exception:
        messages.error(request, "Could not remove the item. Please try again.")

    return redirect('cart')


def _active_cart_items(request):
    """Active cart items for an authed user or a guest session."""
    if request.user.is_authenticated:
        return CartItem.objects.filter(user=request.user, is_active=True)
    cart = Cart.objects.filter(cart_id=_cart_id(request)).first()
    if not cart:
        return CartItem.objects.none()
    return CartItem.objects.filter(cart=cart, is_active=True)


def _estimate_throttled(request) -> bool:
    """Soft per-session throttle for the shipping-estimate endpoint.

    Generous limit (40 calls / 60s) so legitimate re-estimates never hit it; it
    only blunts abusive loops. Best-effort: any cache problem fails open.
    """
    try:
        from django.core.cache import cache
        key = f"ship_estimate_rl:{_cart_id(request)}"
        count = cache.get(key, 0)
        if count >= 40:
            return True
        cache.set(key, count + 1, 60)
    except Exception:
        return False
    return False


@require_POST
def shipping_estimate(request):
    """Pre-order shipping estimate (cost + delivery time) for the current cart.

    CSRF-protected, POST-only. Reads the cart SERVER-SIDE and never trusts any
    client-supplied price or cost. Returns JSON; never creates an order.
    """
    from printify_integration.shipping_estimator import estimate_for_cart
    from shipping.geo import set_manual_country

    if _estimate_throttled(request):
        return JsonResponse({"available": False, "errors_safe": ["rate_limited"],
                             "disclaimer": str(_("Too many requests. Please wait a moment."))},
                            status=429)

    country = (request.POST.get("country") or "").strip().upper()[:2]
    postal_code = (request.POST.get("postal_code") or "").strip()[:16]
    region = (request.POST.get("region") or "").strip()[:64]
    city = (request.POST.get("city") or "").strip()[:64]
    method = (request.POST.get("shipping_method") or "").strip()[:24]

    if len(country) != 2 or not country.isalpha():
        return JsonResponse({"available": False, "errors_safe": ["invalid_country"],
                             "disclaimer": str(_("Please choose a delivery country."))},
                            status=200)

    # Keep the session country in sync so the cart/checkout totals match the estimate.
    set_manual_country(request, country)

    cart_items = list(_active_cart_items(request))
    result = estimate_for_cart(cart_items, country, postal_code=postal_code,
                               region=region, city=city, shipping_method=method)
    return JsonResponse(result.as_dict(), status=200)


def cart(request, total=0, quantity=0, cart_items=None):
    from orders.totals import compute_cart_totals
    from shipping.geo import detect_country

    cart_items = _active_cart_items(request)
    country = detect_country(request)
    totals = compute_cart_totals(cart_items, country)

    # Coupon (re-validated against the current subtotal).
    from decimal import Decimal
    from django.conf import settings
    from promotions.services import applied_coupon
    coupon, discount = applied_coupon(request, totals.items_subtotal)
    grand_total = max(Decimal("0"), Decimal(str(totals.grand_total)) - discount)

    # Free-shipping progress bar.
    threshold = Decimal(str(getattr(settings, "SHIPPING_FREE_THRESHOLD", 0) or 0))
    sub = Decimal(str(totals.items_subtotal))
    free_remaining = max(Decimal("0"), threshold - sub) if threshold else Decimal("0")
    free_progress = min(100, int(sub / threshold * 100)) if threshold else 0

    context = {
        'total': totals.items_subtotal,
        'quantity': totals.quantity,
        'cart_items': cart_items,
        'tax': totals.tax,
        'grand_total': grand_total,
        'shipping_cost': totals.shipping_cost,
        'shipping_quote': totals.shipping_quote,
        'coupon': coupon,
        'discount': discount,
        'free_shipping_threshold': threshold,
        'free_shipping_remaining': free_remaining,
        'free_shipping_progress': free_progress,
        'free_shipping_reached': threshold and sub >= threshold,
    }
    return render(request, 'store/cart.html', context)


def checkout(request, total=0, quantity=0, cart_items=None):
    from orders.totals import compute_cart_totals
    from shipping.geo import detect_country

    cart_items = _active_cart_items(request)
    if not cart_items:
        messages.info(request, "Your cart is empty.")
        return redirect("store")

    country = detect_country(request)
    totals = compute_cart_totals(cart_items, country)
    total = totals.items_subtotal
    quantity = totals.quantity
    tax = totals.tax

    # Re-validate the session coupon against the live subtotal (anti-abuse + min order).
    from decimal import Decimal
    from promotions.services import applied_coupon
    coupon, discount = applied_coupon(request, totals.items_subtotal)
    grand_total = float(max(Decimal("0"), Decimal(str(totals.grand_total)) - discount))

    # Guests check out without an account; no saved addresses.
    if not request.user.is_authenticated:
        prefill = {
            "first_name": "", "last_name": "", "email": "", "phone": "",
            "address_line_1": "", "address_line_2": "", "city": "", "state": "",
            "postal_code": "", "country": country, "order_note": "",
        }
        context = {
            "total": total, "quantity": quantity, "cart_items": cart_items,
            "tax": tax, "grand_total": grand_total, "shipping_cost": totals.shipping_cost,
            "shipping_quote": totals.shipping_quote, "prefill": prefill,
            "addresses": [], "default_addr": None, "is_guest": True,
            "coupon": coupon, "discount": discount,
        }
        return render(request, "store/checkout.html", context)

    raw_qs = Address.objects.filter(user=request.user).order_by("-is_default", "-updated_at", "-id")
    default_addr = raw_qs.filter(is_default=True).first()

    seen = set()
    unique_addresses = []
    for a in raw_qs:
        key = (
            (a.first_name or "").strip().lower(),
            (a.last_name or "").strip().lower(),
            (a.email or "").strip().lower(),
            (a.phone or "").strip().lower(),
            (a.address_line_1 or "").strip().lower(),
            (a.address_line_2 or "").strip().lower(),
            (a.city or "").strip().lower(),
            (a.state or "").strip().lower(),
            (a.postal_code or "").strip().lower(),
            (a.country or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_addresses.append(a)

    addresses = unique_addresses

    prefill = {
        "first_name": request.user.first_name or "",
        "last_name": request.user.last_name or "",
        "email": request.user.email or "",
        "phone": getattr(request.user, "phone_number", "") or "",
        "address_line_1": "",
        "address_line_2": "",
        "city": "",
        "state": "",
        "postal_code": "",
        "country": "",
        "order_note": "",
    }

    if default_addr:
        prefill.update({
            "first_name": default_addr.first_name,
            "last_name": default_addr.last_name,
            "email": default_addr.email,
            "phone": default_addr.phone,
            "address_line_1": default_addr.address_line_1,
            "address_line_2": default_addr.address_line_2,
            "city": default_addr.city,
            "state": default_addr.state,
            "postal_code": getattr(default_addr, "postal_code", "") or "",
            "country": (default_addr.country or "IT"),
        })

    context = {
        "total": total,
        "quantity": quantity,
        "cart_items": cart_items,
        "tax": tax,
        "grand_total": grand_total,
        "shipping_cost": totals.shipping_cost,
        "shipping_quote": totals.shipping_quote,
        "prefill": prefill,
        "addresses": addresses,
        "default_addr": default_addr,
        "is_guest": False,
        "coupon": coupon, "discount": discount,
    }
    return render(request, "store/checkout.html", context)
