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
                "administrativeArea": data.get("state") or "",
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


def _diagnose_403():
    """Premium diagnostic for a Google 403 — the terse 'Key rejected' hid the real causes."""
    return _("Google rejected this key (403). Common causes: the Address Validation API is not "
             "enabled on the project, billing is disabled, the key is restricted to the wrong "
             "application type, this server's IP is not in the key's allowed IPs, or a "
             "referrer-restricted BROWSER key was pasted into the server-key field (a browser "
             "key cannot be tested from the server — use the client-side test instead).")


def test_connection(cfg):
    """Admin 'Test connection' for the SERVER key only — READ-ONLY dummy-address check.

    The browser key is deliberately NEVER tested server-side: a referrer-restricted key
    always 403s outside a browser, which reads as a false negative. The admin page offers a
    client-side test for it instead. Errors are mapped to actionable, key-free messages."""
    from payments import secrets as secretbox
    from payments.secrets import SecretKeyMissing
    if not cfg.has_server_key():
        cfg.record_connection("failed", _("No server key set."))
        return {"ok": False, "detail": "", "error": _("No server key set.")}
    # decrypt() is fail-soft (returns "" without the encryption key) — check explicitly so a
    # missing PAYMENT_CONFIG_KEY yields a precise message instead of a bogus Google call.
    server_key = cfg.get_server_key()
    if not server_key:
        cfg.record_connection("failed", _("Encryption key missing."))
        return {"ok": False, "detail": "",
                "error": _("PAYMENT_CONFIG_KEY is not configured on the server — the stored key "
                           "cannot be decrypted. Configure it, then save the server key again.")}
    try:
        import requests
        resp = requests.post(
            "https://addressvalidation.googleapis.com/v1:validateAddress",
            params={"key": server_key},
            json={"address": {"regionCode": "IT", "postalCode": "20100",
                              "locality": "Milano", "addressLines": ["Via Roma 1"]}},
            timeout=8)
        if resp.status_code in (401, 403):
            err = _diagnose_403()
            cfg.record_connection("failed", _("Key rejected (%d) — see diagnostics.") % resp.status_code)
            return {"ok": False, "detail": "", "error": err}
        if resp.status_code == 400:
            cfg.record_connection("failed", _("Invalid key or malformed request (400)."))
            return {"ok": False, "detail": "",
                    "error": _("Google answered 400 — the key looks malformed or truncated. "
                               "Re-copy it from the Google console.")}
        if resp.status_code == 429:
            cfg.record_connection("failed", _("Quota exceeded (429)."))
            return {"ok": False, "detail": "",
                    "error": _("Quota exceeded (429) — check the project's quotas and billing.")}
        resp.raise_for_status()
        cfg.record_connection("connected", _("Address Validation API reachable."))
        return {"ok": True, "detail": _("Address Validation API reachable."), "error": ""}
    except SecretKeyMissing:
        cfg.record_connection("failed", _("Encryption key missing."))
        return {"ok": False, "detail": "",
                "error": _("PAYMENT_CONFIG_KEY is not configured on the server — the stored key "
                           "cannot be decrypted. Configure it, then save the server key again.")}
    except Exception:
        cfg.record_connection("failed", _("Could not reach Google (network/timeout)."))
        return {"ok": False, "detail": "", "error": _("Could not reach Google (network/timeout).")}


# --------------------------------------------------------------------------- #
# Professional address flow — effective mode + order-time verification
# --------------------------------------------------------------------------- #
def effective_mode(cfg):
    """The mode checkout actually enforces. Strict is only meaningful when SOME Google surface
    is usable (browser autocomplete or server validation); otherwise it degrades to warning so
    a misconfigured admin can never lock every customer out."""
    if cfg is None or not cfg.is_enabled:
        return "disabled"
    mode = getattr(cfg, "validation_mode", "disabled") or "disabled"
    if mode == "strict" and not (cfg.autocomplete_ready() or cfg.validation_ready()):
        return "warning"
    return mode


def verify_for_order(cfg, data, place_id, claimed_verified=False):
    """Order-time server verdict. Returns (ok, error_message).

    STRICT: never trusts hidden fields alone — requires a Places place_id from the suggestion
    flow AND, when the server key is configured, a fail-CLOSED Google Address Validation pass;
    without a server key it falls back to place_id presence + strict local checks (documented
    browser-trust mode). WARNING/DISABLED are handled by the caller's confirm flow.
    No PII is ever logged; no mutation; short timeouts.
    """
    from django.utils.translation import gettext as _
    place_id = (place_id or "").strip()[:128]
    if not place_id or any(ord(c) < 33 for c in place_id):
        return False, _("Please select a verified address from the suggestions.")

    level, _msg = validate_locally(data)
    if level != "ok":
        return False, _("Please double-check the postal code and street, then pick the address "
                        "from the suggestions again.")

    if cfg is not None and cfg.validation_ready():
        # fail-CLOSED in strict: an unreachable validator must not wave orders through
        try:
            import requests
            resp = requests.post(
                "https://addressvalidation.googleapis.com/v1:validateAddress",
                params={"key": cfg.get_server_key()},
                json={"address": {
                    "regionCode": (data.get("country") or "").upper(),
                    "postalCode": data.get("postal_code") or "",
                    "locality": data.get("city") or "",
                    "administrativeArea": data.get("state") or "",
                    "addressLines": [data.get("address_line_1") or ""],
                }},
                timeout=5)
            if resp.status_code != 200:
                logger.info("strict address validation http=%s (fail-closed)", resp.status_code)
                return False, _("We could not verify this address right now — please try again "
                                "in a moment.")
            verdict = (resp.json().get("result") or {}).get("verdict") or {}
            if verdict.get("hasUnconfirmedComponents"):
                return False, _("This address could not be fully verified — please pick it from "
                                "the suggestions or correct it.")
            return True, ""
        except Exception as exc:
            logger.info("strict address validation error=%s (fail-closed)", type(exc).__name__)
            return False, _("We could not verify this address right now — please try again in a "
                            "moment.")
    # no server key: browser-trust mode (place_id from the suggestion flow + local checks)
    return True, ""
