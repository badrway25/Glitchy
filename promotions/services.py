"""Coupon apply/validate, stored in the session and recomputed each cart render."""
from decimal import Decimal

from django.utils.translation import gettext as _

from .models import Coupon, CouponRedemption

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


def quote_for_order(request, subtotal):
    """At checkout / place_order: re-validate the session coupon (incl. per-user limit)
    and return (code, discount) to stash on the pending order. Clears the session coupon
    (it is now bound to this order). Does NOT record a redemption — that happens only when
    the order is actually paid, so abandoned checkouts never burn a one-time coupon."""
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
    discount = coupon.discount_for(subtotal)
    clear(request)
    return code, discount


def finalize_coupon_redemption(order):
    """Record the coupon redemption for a PAID order: atomic, idempotent, exactly-once.
    Reads the code stashed on the order. Safe to call from the web flow OR the Stripe
    webhook (get_or_create on (coupon, order) + row lock prevent double-counting)."""
    from django.db import transaction
    from django.db.models import F

    code = (getattr(order, "coupon_code", "") or "").strip().upper()
    if not code:
        return Decimal("0")
    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().filter(code=code).first()
        if not coupon:
            return Decimal("0")
        _redemption, created = CouponRedemption.objects.get_or_create(
            coupon=coupon, order=order,
            defaults={"user": getattr(order, "user", None),
                      "session_key": getattr(order, "session_key", "") or "",
                      "amount": Decimal(str(getattr(order, "discount", 0) or 0))})
        if created:
            Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)
    return Decimal(str(getattr(order, "discount", 0) or 0))


def clear(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
