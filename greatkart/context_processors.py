"""Project-wide template context."""
import os
from django.conf import settings

_ASSET_BASE = os.path.join(os.path.dirname(__file__), "static")


def seo_globals(request):
    """Canonical URL + EN/IT/FR hreflang alternates for the current page."""
    site = getattr(settings, "SITE_URL", "").rstrip("/")
    path = request.path or "/"
    # Strip an active language prefix to get the unprefixed (EN) path.
    unprefixed = path
    for code in ("it", "fr"):
        if path == f"/{code}" or path.startswith(f"/{code}/"):
            unprefixed = path[len(code) + 1:] or "/"
            break
    return {
        "SITE_URL": site,
        "CANONICAL_URL": site + unprefixed,
        "HREFLANG_ALTERNATES": [
            ("en", site + unprefixed),
            ("it", site + "/it" + unprefixed),
            ("fr", site + "/fr" + unprefixed),
            ("x-default", site + unprefixed),
        ],
    }


def _asset_version():
    """Cache-busting token = newest mtime of our custom css/js assets."""
    latest = 0
    for rel in ("css/premium.css", "css/theme.css", "js/premium.js",
                "js/theme.js", "js/script.js", "js/assistant.js", "js/storefront.js",
                "js/wishlist.js", "js/search.js", "js/growth.js", "js/shopfilters.js"):
        try:
            latest = max(latest, int(os.path.getmtime(os.path.join(_ASSET_BASE, rel))))
        except OSError:
            pass
    return str(latest or 1)


def site_globals(request):
    """Expose brand identity and currency to every template."""
    return {
        "ASSET_VERSION": _asset_version(),
        "SITE_NAME": getattr(settings, "SITE_NAME", "MAISON"),
        "SITE_TAGLINE": getattr(settings, "SITE_TAGLINE", ""),
        "CURRENCY_SYMBOL": getattr(settings, "STORE_CURRENCY_SYMBOL", "€"),
        "RETURN_WINDOW_DAYS": getattr(settings, "RETURN_WINDOW_DAYS", 14),
        "FREE_SHIPPING_THRESHOLD": getattr(settings, "SHIPPING_FREE_THRESHOLD", 0),
        # Social profiles: rendered ONLY when configured via env (no dead placeholder links)
        "SOCIAL_LINKS": [t for t in [
            ("Instagram", "fa-instagram", getattr(settings, "SOCIAL_INSTAGRAM", "")),
            ("TikTok", "fa-tiktok", getattr(settings, "SOCIAL_TIKTOK", "")),
            ("YouTube", "fa-youtube", getattr(settings, "SOCIAL_YOUTUBE", "")),
            ("Facebook", "fa-facebook-f", getattr(settings, "SOCIAL_FACEBOOK", "")),
        ] if t[2]],
        "PAYPAL_CLIENT_ID": getattr(settings, "PAYPAL_CLIENT_ID", ""),
        "PAYPAL_CURRENCY": getattr(settings, "PAYPAL_CURRENCY", "EUR"),
        "PAYPAL_ENABLED": getattr(settings, "PAYPAL_ENABLED", False),
        "STRIPE_CURRENCY": getattr(settings, "STRIPE_CURRENCY", "eur").upper(),
        "SUPPORT_EMAIL": getattr(settings, "SUPPORT_EMAIL", ""),
        "AI_ASSISTANT_ENABLED": getattr(settings, "AI_ASSISTANT_ENABLED", False),
    }
