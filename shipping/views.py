from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .constants import country_name
from .geo import set_manual_country
from .services import fallback_quote, is_country_supported


@require_POST
def set_country(request):
    """Persist a manually chosen shipping country (fallback when IP is unreliable).

    Read-only side effects (a session preference); validates the code and, for AJAX callers,
    returns the SAME honest localized summary the PDP renders (no secrets, no invented data)."""
    country = (request.POST.get("country") or "").strip().upper()
    if len(country) != 2 or not country.isalpha():
        return JsonResponse({"ok": False, "error": "invalid_country"}, status=400)
    set_manual_country(request, country)

    # AJAX callers get a fresh quote back; form posts just bounce home.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from .localization import localize_shipping
        try:
            subtotal = float(request.POST.get("subtotal") or 0)
        except (TypeError, ValueError):
            subtotal = 0.0
        quote = fallback_quote(country, total_quantity=1, subtotal=subtotal)
        return JsonResponse({
            "ok": True,
            "country": country,
            "country_name": country_name(country),
            "supported": is_country_supported(country),
            "quote": quote.as_dict(),
            "localized": localize_shipping(request, subtotal=subtotal),
        })

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "home"
    return redirect(next_url)
