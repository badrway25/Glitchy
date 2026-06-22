"""Server-side PayPal capture verification — FAIL-CLOSED.

The browser can only ever supply a capture/transaction id; it must NEVER be trusted
to assert that money moved. Before an order is finalized we independently ask PayPal's
REST API whether that capture is COMPLETED and whether its amount + currency match the
order. If PayPal is not enabled or the secret is missing, verification returns False, so
no PayPal payment can finalize an order. No secret is ever logged.
"""
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger("orders.paypal")


def paypal_available():
    """True only when PayPal is explicitly enabled AND both credentials are present."""
    return bool(getattr(settings, "PAYPAL_ENABLED", False)
                and getattr(settings, "PAYPAL_CLIENT_ID", "")
                and getattr(settings, "PAYPAL_SECRET", ""))


def _access_token():
    import requests
    base = getattr(settings, "PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")
    resp = requests.post(f"{base}/v1/oauth2/token",
                         auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
                         data={"grant_type": "client_credentials"},
                         headers={"Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("access_token", "")


def verify_capture(capture_id, expected_amount, expected_currency):
    """Return (ok: bool, reason: str). ok=True only if PayPal confirms a COMPLETED
    capture whose amount and currency match the order. Fail-closed on any problem."""
    if not paypal_available():
        return False, "paypal_unavailable"
    if not capture_id:
        return False, "missing_capture"
    try:
        import requests
        base = settings.PAYPAL_API_BASE
        token = _access_token()
        resp = requests.get(f"{base}/v2/payments/captures/{capture_id}",
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"}, timeout=15)
        if resp.status_code != 200:
            return False, "capture_not_found"
        data = resp.json()
    except Exception:
        logger.warning("PayPal verification call failed for a capture (no secret logged)")
        return False, "verification_error"

    if (data.get("status") or "").upper() != "COMPLETED":
        return False, "not_completed"
    amount = (data.get("amount") or {})
    try:
        paid = Decimal(str(amount.get("value", "0")))
    except Exception:
        return False, "bad_amount"
    if paid != Decimal(str(expected_amount)):
        return False, "amount_mismatch"
    if (amount.get("currency_code") or "").upper() != str(expected_currency).upper():
        return False, "currency_mismatch"
    return True, "ok"
