"""Coupon apply/validate, stored in the session and recomputed each cart render."""
from decimal import Decimal

from django.utils.translation import gettext as _

from .models import Coupon

SESSION_KEY = "coupon_code"


def messages_for(reason):
    return {
        "ok": _("Coupon applied."),
        "not_found": _("That coupon code isn't valid."),
        "inactive": _("That coupon code isn't valid."),
        "not_started": _("This coupon isn't active yet."),
        "expired": _("This coupon has expired."),
        "used_up": _("This coupon has reached its usage limit."),
        "min_order": _("Your order doesn't meet this coupon's minimum."),
    }.get(reason, _("That coupon code isn't valid."))


def apply(request, code, subtotal):
    code = (code or "").strip().upper()
    if not code:
        return {"ok": False, "message": messages_for("not_found")}
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        return {"ok": False, "message": messages_for("not_found")}
    ok, reason = coupon.validate(subtotal)
    if not ok:
        return {"ok": False, "message": messages_for(reason)}
    request.session[SESSION_KEY] = code
    request.session.modified = True
    return {"ok": True, "message": messages_for("ok"),
            "discount": str(coupon.discount_for(subtotal)), "code": code}


def applied_coupon(request, subtotal):
    """Return (coupon, discount Decimal) for the session coupon, re-validating it.
    Auto-clears the session coupon if it became invalid (e.g. min order no longer met)."""
    code = request.session.get(SESSION_KEY)
    if not code:
        return None, Decimal("0")
    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        clear(request)
        return None, Decimal("0")
    ok, _reason = coupon.validate(subtotal)
    if not ok:
        return None, Decimal("0")   # keep code in session but no discount until valid
    return coupon, coupon.discount_for(subtotal)


def clear(request):
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
