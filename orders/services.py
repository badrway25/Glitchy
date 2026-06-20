"""
Order finalisation + Printify push services.

Guest-aware: works whether the order belongs to an authenticated Account or an
anonymous session. Snapshots production costs and computes margins, then routes
all customer/internal email through the notifications layer (n8n primary, SMTP
fallback).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from carts.models import Cart, CartItem
from .margins import estimate_payment_fee
from .models import OrderProduct
from .printify import create_order, send_to_production
from .printify_payload import build_printify_payload

logger = logging.getLogger("orders")


# --------------------------------------------------------------------------- #
# Cost helpers
# --------------------------------------------------------------------------- #
def production_cost_for_item(cart_item) -> float:
    """Best available per-unit production cost for a cart line."""
    costs = [
        float(getattr(v, "production_cost", 0) or 0)
        for v in cart_item.variations.all()
    ]
    variant_cost = max(costs) if costs else 0.0
    if variant_cost > 0:
        return variant_cost
    return float(getattr(cart_item.product, "base_cost", 0) or 0)


# --------------------------------------------------------------------------- #
# Printify push (idempotent)
# --------------------------------------------------------------------------- #
def push_order_to_printify(order, *, auto_send=True):
    if order.printify_order_id:
        return order.printify_order_id

    ops = (
        OrderProduct.objects
        .select_related("product")
        .prefetch_related("variations")
        .filter(order=order)
    )

    try:
        payload = build_printify_payload(order=order, order_products=ops)
        res = create_order(payload)

        order.printify_order_id = res.get("id")
        order.printify_status = res.get("status") or "created"
        order.printify_last_error = ""
        order.save(update_fields=["printify_order_id", "printify_status", "printify_last_error"])

        if auto_send and order.printify_order_id:
            send_to_production(order.printify_order_id)
            order.printify_status = "sent_to_production"
            order.save(update_fields=["printify_status"])

        return order.printify_order_id

    except Exception as exc:
        order.printify_status = "error"
        order.printify_last_error = str(exc)
        order.save(update_fields=["printify_status", "printify_last_error"])
        # Internal alert (best-effort).
        try:
            from notifications.notify import notify_printify_error

            notify_printify_error(order, str(exc))
        except Exception:
            pass
        raise


# --------------------------------------------------------------------------- #
# Finalisation
# --------------------------------------------------------------------------- #
def _cart_items_for(request, order):
    """Resolve the active cart for either an authed user or a guest session."""
    if order.user_id and request.user.is_authenticated:
        return CartItem.objects.select_related("product").prefetch_related("variations").filter(
            user=request.user, is_active=True)
    # Guest: by session cart.
    session_key = order.session_key or request.session.session_key
    if not session_key:
        return CartItem.objects.none()
    cart = Cart.objects.filter(cart_id=session_key).first()
    if not cart:
        return CartItem.objects.none()
    return CartItem.objects.select_related("product").prefetch_related("variations").filter(
        cart=cart, is_active=True)


@transaction.atomic
def finalize_order_payment(*, request, order, payment):
    """
    Attach payment, convert cart → OrderProduct, snapshot costs/margins,
    decrement stock, clear cart, and fire notifications.
    """
    order.payment = payment
    order.is_ordered = True
    order.status = "Accepted"

    cart_items = list(_cart_items_for(request, order))

    total_production_cost = 0.0
    for item in cart_items:
        unit_cost = production_cost_for_item(item)
        op = OrderProduct.objects.create(
            order_id=order.id,
            payment=payment,
            user=order.user,  # None for guests
            product_id=item.product_id,
            quantity=item.quantity,
            product_price=item.product.price,
            production_cost=unit_cost,
            ordered=True,
        )
        op.variations.set(item.variations.all())
        total_production_cost += unit_cost * int(item.quantity)

        # reduce stock
        product = item.product
        product.stock = max(0, product.stock - item.quantity)
        if product.stock <= 0:
            product.is_available = False
        product.save(update_fields=["stock", "is_available"])

    # --- Cost / margin snapshot ---
    order.cost_production = round(total_production_cost, 2)
    # Our shipping cost: if Printify rate unknown, approximate as what we charged.
    if not order.cost_shipping:
        order.cost_shipping = round(float(order.shipping_cost or 0), 2)
    order.payment_fee = estimate_payment_fee(
        order.order_total,
        percent=getattr(settings, "PAYMENT_FEE_PERCENT", 0),
        fixed=getattr(settings, "PAYMENT_FEE_FIXED", 0),
    )
    order.save()

    # Clear the cart (user OR guest).
    if order.user_id:
        CartItem.objects.filter(user_id=order.user_id).delete()
    elif order.session_key:
        cart = Cart.objects.filter(cart_id=order.session_key).first()
        if cart:
            CartItem.objects.filter(cart=cart).delete()

    # Push to Printify (test mode: don't auto-send to production from web flow).
    try:
        push_order_to_printify(order, auto_send=False)
    except Exception:
        pass  # error already recorded on the order

    # --- Notifications (n8n primary, SMTP fallback) ---
    try:
        from notifications.notify import notify_order_event, notify_negative_margin
        from notifications import events as ev

        notify_order_event(order, ev.ORDER_PAID)
        notify_negative_margin(order)
    except Exception as exc:
        logger.warning("Order notification failed for %s: %s", order.order_number, exc)
