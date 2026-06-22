"""Coupon apply/validate, stored in the session and recomputed each cart render."""
import logging
from decimal import Decimal

from django.db import IntegrityError
from django.utils.translation import gettext as _

from .models import Coupon, CouponRedemption

logger = logging.getLogger(__name__)
SESSION_KEY = "coupon_code"


def messages_for(reason):
    return {
        "ok": _("Coupon applied."),
        "not_found": _("That coupon code isn't valid."),
        "inactive": _("That coupon code isn't valid."),
        "not_started": _("This coupon isn't active yet."),
        "expired": _("This coupon has expired."),
        "used_up": _("This coupon has reached its usage limit."),
        "already_used": _("You've already used this coupon."),
        "min_order": _("Your order doesn't meet this coupon's minimum."),
    }.get(reason, _("That coupon code isn't valid."))


def apply(request, code, subtotal):
    code = (code or "").strip().upper()
    if not code:
        return {"ok": False, "message": messages_for("not_found")}
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        return {"ok": False, "message": messages_for("not_found")}
    ok, reason = coupon.validate(subtotal, request=request)
    if not ok:
        return {"ok": False, "message": messages_for(reason)}
    request.session[SESSION_KEY] = code
    request.session.modified = True
    return {"ok": True, "message": messages_for("ok"),
            "discount": str(coupon.discount_for(subtotal)), "code": code}


def applied_coupon(request, subtotal):
    """Return (coupon, discount Decimal) for the session coupon, re-validating it
    (including the per-user limit). Returns no discount if it became invalid."""
    code = request.session.get(SESSION_KEY)
    if not code:
        return None, Decimal("0")
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        clear(request)
        return None, Decimal("0")
    ok, _reason = coupon.validate(subtotal, request=request)
    if not ok:
        return None, Decimal("0")   # keep code in session but no discount until valid
    return coupon, coupon.discount_for(subtotal)


def _user_redemption_count(coupon, *, user_id, session_key):
    """How many times this coupon has already been redeemed by the given user/guest."""
    if user_id:
        return coupon.redemptions.filter(user_id=user_id).count()
    if session_key:
        return coupon.redemptions.filter(session_key=session_key).count()
    return 0


def _pending_orders_with_coupon(code, *, user_id, session_key, exclude_order_id=None):
    """Count the customer's OTHER unpaid orders that already carry this coupon, so the
    same one-time coupon cannot be stashed on a second order before the first is paid."""
    from orders.models import Order
    qs = Order.objects.filter(coupon_code=code, is_ordered=False)
    if exclude_order_id:
        qs = qs.exclude(pk=exclude_order_id)
    if user_id:
        return qs.filter(user_id=user_id).count()
    if session_key:
        return qs.filter(session_key=session_key).count()
    return 0


def quote_for_order(request, subtotal):
    """At checkout / place_order: re-validate the session coupon (incl. per-user limit)
    and return (code, discount) to stash on the pending order. Clears the session coupon
    (it is now bound to this order). Does NOT record a redemption — that happens only when
    the order is actually paid, so abandoned checkouts never burn a one-time coupon.

    Also counts the customer's OTHER pending orders already carrying this coupon, so a
    per-user/one-time coupon can't be stashed on two orders before either is paid."""
    code = request.session.get(SESSION_KEY)
    if not code:
        return "", Decimal("0")
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        clear(request)
        return "", Decimal("0")
    ok, _reason = coupon.validate(subtotal, request=request)
    if not ok:
        clear(request)
        return "", Decimal("0")
    # Belt-and-suspenders: redemptions already made + coupon stashed on other pending orders.
    if coupon.per_user_limit:
        user_id = request.user.id if request.user.is_authenticated else None
        sk = "" if user_id else (request.session.session_key or "")
        already = (_user_redemption_count(coupon, user_id=user_id, session_key=sk)
                   + _pending_orders_with_coupon(code, user_id=user_id, session_key=sk))
        if already >= coupon.per_user_limit:
            clear(request)
            return "", Decimal("0")
    discount = coupon.discount_for(subtotal)
    clear(request)
    return code, discount


def finalize_coupon_redemption(order):
    """Authoritative coupon gate, run when the order is PAID. Atomic + idempotent +
    serialized on the coupon row, so it is correct even for two near-simultaneous paid
    orders or a duplicated Stripe webhook:

      * locks the coupon row (select_for_update) → finalizations serialize;
      * idempotent per order (returns early if this order already has a redemption);
      * re-checks per_user_limit and usage_limit UNDER THE LOCK;
      * if the coupon is no longer redeemable, the already-paid order is HONORED as-is
        (the customer paid the discounted total) but NO extra redemption is recorded and
        used_count is NOT incremented — a safe event is logged. No order is corrupted.
    """
    from django.db import transaction
    from django.db.models import F

    code = (getattr(order, "coupon_code", "") or "").strip().upper()
    if not code:
        return Decimal("0")
    amount = Decimal(str(getattr(order, "discount", 0) or 0))
    user_id = getattr(order, "user_id", None)
    session_key = getattr(order, "session_key", "") or ""

    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().filter(code=code).first()
        if not coupon:
            return Decimal("0")
        # Idempotency: this exact order already redeemed (duplicate webhook / re-confirm).
        if CouponRedemption.objects.filter(coupon=coupon, order=order).exists():
            return amount
        # Per-user / per-guest cap, re-checked while holding the coupon lock.
        if coupon.per_user_limit and _user_redemption_count(
                coupon, user_id=user_id, session_key=session_key) >= coupon.per_user_limit:
            logger.warning("coupon %s over per-user limit at finalize for order %s — honored, not re-recorded",
                           code, getattr(order, "order_number", "?"))
            return amount
        # Global usage cap.
        if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
            logger.warning("coupon %s over usage limit at finalize for order %s — honored, not re-recorded",
                           code, getattr(order, "order_number", "?"))
            return amount
        try:
            CouponRedemption.objects.create(
                coupon=coupon, order=order, user_id=user_id,
                session_key="" if user_id else session_key, amount=amount)
        except IntegrityError:
            # The (coupon, order) unique constraint fired in a concurrent finalize.
            return amount
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)
    return amount


def clear(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
