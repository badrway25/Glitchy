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
    """True only when PayPal is enabled AND both credentials are present (admin config or env).
    Credentials resolve DB-first (payments.config) then fall back to env — see the resolver."""
    from payments import config as pc
    return pc.paypal_available()


def _access_token():
    import requests
    from payments import config as pc
    base = pc.paypal_api_base()
    resp = requests.post(f"{base}/v1/oauth2/token",
                         auth=(pc.paypal_client_id(), pc.paypal_secret()),
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
        from payments import config as pc
        base = pc.paypal_api_base()
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


def create_order(payload):
    """Create a PayPal Orders v2 order SERVER-SIDE from the trusted payload.

    Returns (order_id, error_code). Fail-closed: no config → no order. Logs only safe
    codes (never token, payload PII or secrets)."""
    if not paypal_available():
        return None, "paypal_unavailable"
    import requests
    from payments import config as pc
    try:
        token = _access_token()
        resp = requests.post(
            f"{pc.paypal_api_base()}/v2/checkout/orders",
            json=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            timeout=20)
        if resp.status_code in (200, 201):
            oid = resp.json().get("id")
            return (oid, "") if oid else (None, "no_order_id")
        # safe diagnostics: PayPal's issue code only (no PII echo)
        try:
            issue = (resp.json().get("details") or [{}])[0].get("issue", "")
        except Exception:
            issue = ""
        logging.getLogger("orders").warning(
            "paypal create order failed http=%s issue=%s", resp.status_code, issue or "?")
        return None, issue or f"http_{resp.status_code}"
    except Exception as exc:
        logging.getLogger("orders").warning(
            "paypal create order error=%s", type(exc).__name__)
        return None, "network"


def capture_order(paypal_order_id):
    """SERVER-SIDE capture of an approved Orders v2 order.

    Returns (result, issue): result = {"status","capture_id","amount","currency"} on any
    parseable outcome, None on transport failure; issue = PayPal issue code / safe reason.
    Replaces the client-side actions.order.capture() that hung against server-created
    orders. Never logs tokens or payer data."""
    if not paypal_available():
        return None, "paypal_unavailable"
    import requests
    from payments import config as pc
    oid = (paypal_order_id or "").strip()[:64]
    if not oid or not all(c.isalnum() or c in "-_" for c in oid):
        return None, "invalid_order_id"
    try:
        token = _access_token()
        resp = requests.post(
            f"{pc.paypal_api_base()}/v2/checkout/orders/{oid}/capture",
            json={},
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            timeout=25)
        try:
            data = resp.json()
        except Exception:
            data = {}
        if resp.status_code in (200, 201):
            status = data.get("status", "")
            cap, amount, currency = "", "", ""
            try:
                c0 = data["purchase_units"][0]["payments"]["captures"][0]
                cap = c0.get("id", "")
                amount = (c0.get("amount") or {}).get("value", "")
                currency = (c0.get("amount") or {}).get("currency_code", "")
            except Exception:
                pass
            return {"status": status, "capture_id": cap,
                    "amount": amount, "currency": currency}, ""
        issue = ""
        try:
            issue = (data.get("details") or [{}])[0].get("issue", "")
        except Exception:
            pass
        logging.getLogger("orders").warning(
            "paypal capture failed http=%s issue=%s", resp.status_code, issue or "?")
        return None, issue or f"http_{resp.status_code}"
    except Exception as exc:
        logging.getLogger("orders").warning("paypal capture error=%s", type(exc).__name__)
        return None, "network"
