from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .constants import country_name
from .geo import set_manual_country
from .services import fallback_quote, is_country_supported


@require_POST
def set_country(request):
    """Persist a manually chosen shipping country (fallback when IP is unreliable)."""
    country = (request.POST.get("country") or "").strip().upper()
    set_manual_country(request, country)

    # AJAX callers get a fresh quote back; form posts just bounce home.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        quote = fallback_quote(country, total_quantity=1, subtotal=0)
        return JsonResponse({
            "ok": True,
            "country": country,
            "country_name": country_name(country),
            "supported": is_country_supported(country),
            "quote": quote.as_dict(),
        })

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "home"
    return redirect(next_url)
