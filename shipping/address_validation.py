"""Server-side address validation — local rules always, Google Address Validation optionally.

Philosophy: NEVER block a legitimate order. Local checks catch obvious garbage; the Google
API (when configured) can only produce a *warning* asking the shopper to review — a
"my address is correct" confirmation always lets them proceed. The API call is read-only,
short-timeout, fail-open, and no full address is ever logged.
"""
import logging
import re

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

# very light per-country postal-code shapes (only where unambiguous — warning-only)
_POSTAL_SHAPES = {
    "IT": r"^\d{5}$", "FR": r"^\d{5}$", "DE": r"^\d{5}$", "ES": r"^\d{5}$",
    "BE": r"^\d{4}$", "AT": r"^\d{4}$", "CH": r"^\d{4}$", "NL": r"^\d{4}\s?[A-Za-z]{2}$",
    "PT": r"^\d{4}-?\d{3}$", "US": r"^\d{5}(-\d{4})?$", "CA": r"^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$",
    "GB": r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}$", "IE": r".{3,}", "AU": r"^\d{4}$",
}


def validate_locally(data):
    """Cheap, dependency-free checks. Returns (level, message) — level in ok|warning."""
    country = (data.get("country") or "").upper()
    postal = (data.get("postal_code") or "").strip()
    shape = _POSTAL_SHAPES.get(country)
    if shape and postal and not re.match(shape, postal):
        return "warning", _("The postal code doesn't look like a valid %(c)s postal code — "
                            "please double-check it.") % {"c": country}
    addr = (data.get("address_line_1") or "").strip()
    if addr and not re.search(r"\d", addr) and len(addr) < 8:
        return "warning", _("The address looks incomplete — please include the street and number.")
    return "ok", ""


def validate_with_google(cfg, data):
    """Optional read-only Google Address Validation. Warning-only, fail-open.

    Never raises; never logs the address or the key; 4s timeout."""
    try:
        import requests
        key = cfg.get_server_key()
        if not key:
            return "ok", ""
        body = {
            "address": {
                "regionCode": (data.get("country") or "").upper(),
                "postalCode": data.get("postal_code") or "",
                "locality": data.get("city") or "",
                "addressLines": [data.get("address_line_1") or ""],
            }
        }
        resp = requests.post(
            "https://addressvalidation.googleapis.com/v1:validateAddress",
            params={"key": key}, json=body, timeout=4)
        if resp.status_code != 200:
            logger.info("address validation api status=%s (fail-open)", resp.status_code)
            return "ok", ""
        verdict = (resp.json().get("result") or {}).get("verdict") or {}
        if verdict.get("hasUnconfirmedComponents"):
            return "warning", _("We could not fully verify this address. You can correct it, "
                                "or continue if you are sure it is right.")
        return "ok", ""
    except Exception as exc:                      # network/timeout/parse — never block checkout
        logger.info("address validation skipped: %s (fail-open)", type(exc).__name__)
        return "ok", ""


def validate_address(data, cfg=None):
    """Combined validation: local always; Google only when the admin enabled it."""
    level, msg = validate_locally(data)
    if level != "ok":
        return level, msg
    if cfg is not None and cfg.validation_ready():
        return validate_with_google(cfg, data)
    return "ok", ""


def test_connection(cfg):
    """Admin 'Test connection' — READ-ONLY: validates a fixed dummy address. Safe report."""
    if not cfg.has_server_key():
        cfg.record_connection("failed", _("No server key set."))
        return {"ok": False, "detail": "", "error": _("No server key set.")}
    try:
        import requests
        resp = requests.post(
            "https://addressvalidation.googleapis.com/v1:validateAddress",
            params={"key": cfg.get_server_key()},
            json={"address": {"regionCode": "IT", "postalCode": "20100",
                              "locality": "Milano", "addressLines": ["Via Roma 1"]}},
            timeout=8)
        if resp.status_code in (401, 403):
            cfg.record_connection("failed", _("Key rejected (%d).") % resp.status_code)
            return {"ok": False, "detail": "", "error": _("Key rejected (%d).") % resp.status_code}
        resp.raise_for_status()
        cfg.record_connection("connected", _("Address Validation API reachable."))
        return {"ok": True, "detail": _("Address Validation API reachable."), "error": ""}
    except Exception:
        cfg.record_connection("failed", _("Could not reach Google (network/timeout)."))
        return {"ok": False, "detail": "", "error": _("Could not reach Google (network/timeout).")}
