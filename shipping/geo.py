"""
Lightweight, dependency-free country detection from the request.

Priority order (highest first):
    1. Explicit manual choice stored in the session (user picked a country).
2. CDN / proxy country headers (Cloudflare `CF-IPCountry`, generic `X-Country`).
    3. GeoIP2 lookup *if* the optional `geoip2` library + database are installed.
    4. Optional external IP geolocation API (off by default; opt-in via settings).
    5. `settings.SHIPPING_DEFAULT_COUNTRY` fallback.

The final shipping address always wins at checkout — this module only provides
the *estimate* shown before the address is known.
"""
from __future__ import annotations

import ipaddress
import json
import urllib.request

from django.conf import settings

SESSION_KEY = "ship_country"
_PRIVATE_OK = ("127.0.0.1", "::1", "localhost")


def get_client_ip(request) -> str | None:
    """Best-effort extraction of the originating client IP."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # First entry is the original client.
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _is_public_ip(ip: str | None) -> bool:
    if not ip or ip in _PRIVATE_OK:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local)


def _from_headers(request) -> str | None:
    for header in ("HTTP_CF_IPCOUNTRY", "HTTP_X_COUNTRY", "HTTP_X_APPENGINE_COUNTRY"):
        val = (request.META.get(header) or "").strip().upper()
        if val and len(val) == 2 and val.isalpha() and val != "XX":
            return val
    return None


def _from_geoip2(ip: str) -> str | None:
    try:
        from django.contrib.gis.geoip2 import GeoIP2  # noqa: WPS433

        return (GeoIP2().country_code(ip) or "").upper() or None
    except Exception:
        return None


def _from_api(ip: str) -> str | None:
    """Opt-in external lookup. Disabled unless SHIPPING_GEOIP_API is True."""
    if not getattr(settings, "SHIPPING_GEOIP_API", False):
        return None
    try:
        url = f"https://ipapi.co/{ip}/country/"
        req = urllib.request.Request(url, headers={"User-Agent": "greatkart/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:  # noqa: S310
            code = resp.read().decode("utf-8").strip().upper()
        if len(code) == 2 and code.isalpha():
            return code
    except Exception:
        return None
    return None


AUTO_KEY = "ship_country_auto"      # cached best-effort detection (once per visitor, discreet)


def detect_country_info(request) -> dict:
    """Best-effort country + HOW we know it: {"code": "FR", "source": "..."}.

    source ∈ manual (user picked), header (CDN country header), cached (earlier auto-detect),
    ip (geo lookup), default (nothing detected — an ASSUMPTION, not knowledge). Callers that
    show customer-facing copy must treat source=="default" as "unknown destination" and use
    neutral "calculated at checkout" wording instead of presenting the default as fact.
    Detection stays discreet and server-side (no precise browser geolocation, no consent-less
    external calls)."""
    default = getattr(settings, "SHIPPING_DEFAULT_COUNTRY", "IT")

    # 1. Manual override (country switcher) — always wins.
    manual = (request.session.get(SESSION_KEY) or "").strip().upper()
    if manual and len(manual) == 2:
        return {"code": manual, "source": "manual"}

    # 2. CDN / proxy headers (fresh every request — cheap, reflects the real visitor).
    header_country = _from_headers(request)
    if header_country:
        request.session[AUTO_KEY] = header_country
        return {"code": header_country, "source": "header"}

    # 3. Cached auto-detection from a previous request (avoids repeat IP lookups).
    cached = (request.session.get(AUTO_KEY) or "").strip().upper()
    if cached and len(cached) == 2:
        return {"code": cached, "source": "cached"}

    # 4. IP-based lookups (only for routable public IPs); cache the result.
    ip = get_client_ip(request)
    if _is_public_ip(ip):
        for resolver in (_from_geoip2, _from_api):
            code = resolver(ip)
            if code:
                request.session[AUTO_KEY] = code
                return {"code": code, "source": "ip"}

    # 5. Fallback (not cached, so detection can still succeed on a later request).
    return {"code": default, "source": "default"}


def detect_country(request) -> str:
    """Return a best-effort ISO-3166 alpha-2 country code (never empty). See detect_country_info."""
    return detect_country_info(request)["code"]


def set_manual_country(request, country: str) -> None:
    """Persist a user's manual country choice in the session."""
    code = (country or "").strip().upper()
    if len(code) == 2 and code.isalpha():
        request.session[SESSION_KEY] = code
