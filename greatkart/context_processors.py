"""Project-wide template context."""
from django.conf import settings


def site_globals(request):
    """Expose brand identity and currency to every template."""
    return {
        "SITE_NAME": getattr(settings, "SITE_NAME", "MAISON"),
        "SITE_TAGLINE": getattr(settings, "SITE_TAGLINE", ""),
        "CURRENCY_SYMBOL": getattr(settings, "STORE_CURRENCY_SYMBOL", "€"),
        "RETURN_WINDOW_DAYS": getattr(settings, "RETURN_WINDOW_DAYS", 14),
        "FREE_SHIPPING_THRESHOLD": getattr(settings, "SHIPPING_FREE_THRESHOLD", 0),
    }
