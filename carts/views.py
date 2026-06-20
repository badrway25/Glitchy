from django.shortcuts import render, redirect, get_object_or_404
from store.models import Product, Variation
from .models import Cart, CartItem
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required
from accounts.models import Address
from django.http import HttpResponse
from django.contrib import messages


def _cart_id(request):
    cart = request.session.session_key
    if not cart:
        cart = request.session.create()
    return cart


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


def cart(request, total=0, quantity=0, cart_items=None):
    from orders.totals import compute_cart_totals
    from shipping.geo import detect_country

    cart_items = _active_cart_items(request)
    country = detect_country(request)
    totals = compute_cart_totals(cart_items, country)

    context = {
        'total': totals.items_subtotal,
        'quantity': totals.quantity,
        'cart_items': cart_items,
        'tax': totals.tax,
        'grand_total': totals.grand_total,
        'shipping_cost': totals.shipping_cost,
        'shipping_quote': totals.shipping_quote,
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
    grand_total = totals.grand_total

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
    }
    return render(request, "store/checkout.html", context)
