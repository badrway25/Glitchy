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


def production_cost_for_order_product(op) -> float:
    """Best available per-unit production cost for an order line (from current data)."""
    costs = [float(getattr(v, "production_cost", 0) or 0) for v in op.variations.all()]
    variant_cost = max(costs) if costs else 0.0
    if variant_cost > 0:
        return variant_cost
    return float(getattr(op.product, "base_cost", 0) or 0)


def backfill_order_costs(*, only_zero=True, dry_run=False):
    """
    Estimate costs/margins for historical orders that predate the cost fields.

    SAFE: production cost is backfilled ONLY from real synced product/variant
    data — never fabricated. Payment fee uses the configured formula; shipping
    cost is proxied from what the customer was charged (only when known).
    Returns a summary dict.
    """
    from django.conf import settings as dj_settings

    from .models import Order, OrderProduct

    qs = Order.objects.filter(is_ordered=True)
    if only_zero:
        qs = qs.filter(cost_production=0)

    summary = {"examined": 0, "updated": 0, "full_cost": 0, "partial_cost": 0,
               "no_cost_data": 0}
    for order in qs:
        summary["examined"] += 1
        ops = list(OrderProduct.objects.prefetch_related("variations", "product").filter(order=order))
        if not ops:
            continue

        prod_cost = 0.0
        lines_with_cost = 0
        for op in ops:
            unit = production_cost_for_order_product(op)
            if unit > 0:
                lines_with_cost += 1
            prod_cost += unit * int(op.quantity)

        if lines_with_cost == 0:
            summary["no_cost_data"] += 1
        elif lines_with_cost == len(ops):
            summary["full_cost"] += 1
        else:
            summary["partial_cost"] += 1

        fee = estimate_payment_fee(
            order.order_total,
            percent=getattr(dj_settings, "PAYMENT_FEE_PERCENT", 0),
            fixed=getattr(dj_settings, "PAYMENT_FEE_FIXED", 0),
        )
        ship = float(order.shipping_cost or 0)

        if not dry_run:
            changed = []
            if prod_cost > 0 and not order.cost_production:
                order.cost_production = round(prod_cost, 2)
                changed.append("cost_production")
            if ship > 0 and not order.cost_shipping:
                order.cost_shipping = round(ship, 2)
                changed.append("cost_shipping")
            if fee > 0 and not order.payment_fee:
                order.payment_fee = fee
                changed.append("payment_fee")
            if changed:
                order.save(update_fields=changed + ["updated_at"])
                summary["updated"] += 1
    return summary


# --------------------------------------------------------------------------- #
# Printify push (idempotent)
# --------------------------------------------------------------------------- #
def push_order_to_printify(order, *, auto_send=True):
    if order.printify_order_id:
        return order.printify_order_id

    # Safety guard: skip real Printify order creation during dry-runs.
    if not getattr(settings, "PRINTIFY_PUSH_ENABLED", True):
        order.printify_status = "push_disabled"
        order.save(update_fields=["printify_status"])
        logger.info("Printify push disabled — skipped for order %s", order.order_number)
        return None

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
def _cart_items_for_order(order):
    """Resolve the active cart from the ORDER (no request needed → webhook-safe)."""
    if order.user_id:
        return CartItem.objects.select_related("product").prefetch_related("variations").filter(
            user_id=order.user_id, is_active=True)
    # Guest: by session cart stored on the order.
    session_key = order.session_key
    if not session_key:
        return CartItem.objects.none()
    cart = Cart.objects.filter(cart_id=session_key).first()
    if not cart:
        return CartItem.objects.none()
    return CartItem.objects.select_related("product").prefetch_related("variations").filter(
        cart=cart, is_active=True)


@transaction.atomic
def finalize_order_payment(*, order, payment, request=None):
    """
    Attach payment, convert cart → OrderProduct, snapshot costs/margins,
    decrement stock, clear cart, and fire notifications.

    Idempotent + request-independent: callable from the web flow OR the Stripe
    webhook. `request` is accepted for backward-compatibility but unused.
    """
    # Idempotency guard: never finalize twice.
    if order.is_ordered and order.orderproduct_set.exists():
        return

    order.payment = payment
    order.is_ordered = True
    order.status = "Accepted"

    cart_items = list(_cart_items_for_order(order))

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
        # carry the colour-matched image snapshot across (the cart rows are
        # deleted below); if the cart line never got one, resolve it now so
        # historical orders keep the purchased colour's mockup
        selected_image = item.selected_image
        if selected_image is None or selected_image.product_id != item.product_id:
            from store.variant_thumbnail import resolve_variant_image
            selected_image = resolve_variant_image(
                item.product, variations=item.variations.all())
        if selected_image is not None:
            op.selected_image = selected_image
            op.save(update_fields=["selected_image"])
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

    # Record the coupon redemption now that the order is paid (atomic, idempotent).
    try:
        from promotions.services import finalize_coupon_redemption
        finalize_coupon_redemption(order)
    except Exception:
        logger.warning("coupon redemption recording skipped for %s", order.order_number)

    # Clear the cart (user OR guest).
    if order.user_id:
        CartItem.objects.filter(user_id=order.user_id).delete()
    elif order.session_key:
        cart = Cart.objects.filter(cart_id=order.session_key).first()
        if cart:
            CartItem.objects.filter(cart=cart).delete()

    # Slow EXTERNAL side-effects (Printify push, n8n/SMTP notifications) run in a background
    # thread: on a slow SMTP they took ~1 minute INSIDE the capture request, so the frontend
    # timed out and told a paid customer "do NOT pay again" while the DB was already
    # completed. The DB core above stays synchronous; these are fire-and-forget and each
    # guards its own failures.
    import threading
    threading.Thread(target=_post_finalize_side_effects, args=(order,), daemon=True).start()


def _post_finalize_side_effects(order):
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


# --------------------------------------------------------------------------- #
# Stripe webhook helpers (request-less, idempotent)
# --------------------------------------------------------------------------- #
def finalize_from_intent(*, order_number, intent_id, intent_status="succeeded",
                         amount=None, email=""):
    """
    Idempotently finalize an order from a confirmed Stripe PaymentIntent.

    Returns (order, result) where result ∈ {"finalized","already_finalized",
    "order_not_found"}. Safe to call multiple times for the same event.
    """
    from .models import Order, Payment

    order = Order.objects.filter(order_number=order_number).first()
    if not order:
        logger.warning("Stripe webhook: order %s not found", order_number)
        return None, "order_not_found"

    if order.is_ordered:
        return order, "already_finalized"

    payment, _created = Payment.objects.get_or_create(
        payment_id=intent_id,
        defaults={
            "user": order.user,
            "email": order.email or email,
            "payment_method": "Stripe",
            "amount_paid": str(amount if amount is not None else order.order_total),
            "status": intent_status or "succeeded",
        },
    )
    finalize_order_payment(order=order, payment=payment)
    logger.info("Stripe webhook finalized order %s", order_number)
    return order, "finalized"


def apply_stripe_refund(*, payment_intent_id, amount_refunded_cents):
    """
    Idempotently record a Stripe refund on the matching order.

    `amount_refunded_cents` is Stripe's CUMULATIVE refunded amount on the charge,
    so we SET (not add) → calling twice is safe.
    """
    from .models import Order, Payment

    payment = Payment.objects.filter(payment_id=payment_intent_id).first()
    if not payment:
        logger.warning("Stripe refund: no payment for intent")
        return None
    order = Order.objects.filter(payment=payment).order_by("-created_at").first()
    if not order:
        return None
    refunded = round(float(amount_refunded_cents or 0) / 100.0, 2)
    if refunded > float(order.refunded_amount or 0):
        order.refunded_amount = refunded
        order.save(update_fields=["refunded_amount", "updated_at"])
        try:
            from notifications.notify import notify_negative_margin
            notify_negative_margin(order)
        except Exception:
            pass
    return order
