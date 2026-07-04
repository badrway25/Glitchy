"""Customer-facing shipping localization — ONE honest source for "Ships to …" copy.

Returns a structured summary the PDP / cart / AJAX endpoint render from. Golden rule: never
present an assumption as a fact. If the destination is only the configured default (nothing was
detected and the user chose nothing), the copy must fall back to "calculated at checkout" — we
never show another visitor "Ships to Italy · €4.90 · 3–6 days" as if we knew.

All figures come from the SAME rate table the cart/checkout estimator and the order snapshot use
(`shipping.services.fallback_quote` — see the settings note: door-to-door business days).
"""
from django.conf import settings
from django.utils.translation import gettext as _

from .constants import COUNTRY_NAMES, country_name
from .geo import detect_country_info
from .services import fallback_quote


def localize_shipping(request, *, subtotal=None, quantity=1):
    """Build the honest shipping summary for the current visitor.

    Keys: country_code, country_name, known (bool — did we actually detect/choose it?),
    supported, free, shipping_cost_label, eta_label, is_estimated, source, is_fallback,
    free_threshold (float|None), line_label (ready-made sentence for simple renders).
    """
    info = detect_country_info(request)
    code, source = info["code"], info["source"]
    known = source in ("manual", "header", "cached", "ip")
    symbol = getattr(settings, "STORE_CURRENCY_SYMBOL", "€")
    threshold = float(getattr(settings, "SHIPPING_FREE_THRESHOLD", 0) or 0)

    out = {
        "country_code": code,
        "country_name": country_name(code),
        "known": known,
        "source": source,
        "supported": False,
        "free": False,
        "shipping_cost_label": "",
        "eta_label": "",
        "is_estimated": True,
        "is_fallback": not known,
        "free_threshold": threshold or None,
        "line_label": "",
    }

    if not known or code not in COUNTRY_NAMES:
        # Destination unknown (or outside the curated list, so we have no presentable
        # name) → neutral truth. The checkout estimator still quotes the configured
        # worldwide default rate for any destination we ship to.
        out["is_fallback"] = True
        out["line_label"] = _("Shipping calculated at checkout based on destination")
        return out

    fq = fallback_quote(code, total_quantity=max(1, int(quantity or 1)), subtotal=float(subtotal or 0))
    if not fq.available:
        # We know the country but have no configured rate for it.
        out["line_label"] = _("Ships to %(country)s · calculated at checkout") % {
            "country": out["country_name"]}
        return out

    out["supported"] = True
    out["free"] = bool(fq.free)
    out["eta_label"] = str(fq.eta_label)
    if fq.free:
        out["shipping_cost_label"] = _("Free shipping")
    else:
        out["shipping_cost_label"] = f"{symbol}{fq.cost:.2f}"
    out["line_label"] = "%s · %s · %s" % (
        _("Ships to %(country)s") % {"country": out["country_name"]},
        out["shipping_cost_label"], out["eta_label"])
    return out
