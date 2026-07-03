"""Read-only payment provider connection tests + safe reporting.

Strictly read-only: Stripe uses Account/Balance retrieve; PayPal fetches an OAuth token and
reads merchant/app info. NEVER creates a PaymentIntent/Checkout Session/Order, never captures,
never refunds. Secrets are decrypted server-side and never returned/logged. Errors are mapped
to short, non-sensitive messages.
"""
from django.utils import timezone


def _finish(cfg, status, detail="", error=""):
    cfg.last_connection_check_at = timezone.now()
    cfg.last_connection_status = status
    cfg.last_connection_detail_safe = (detail or "")[:300]
    cfg.last_connection_error_safe = (error or "")[:200]
    cfg.save(update_fields=["last_connection_check_at", "last_connection_status",
                            "last_connection_detail_safe", "last_connection_error_safe"])
    from .models import PaymentEvent
    PaymentEvent.log(cfg.provider, PaymentEvent.KIND_TEST, ok=(status == "connected"),
                     status=status, reason_safe=error or detail[:200])
    return {"ok": status == "connected", "status": status, "detail": detail, "error": error}


def test_stripe(cfg):
    """Read-only Stripe check via Account/Balance retrieve. No charge is ever created."""
    secret = cfg.get_secret("stripe_secret_key")
    if not secret:
        return _finish(cfg, "failed", error="No secret key set.")
    live_key = secret.startswith("sk_live_")
    if live_key and not cfg.is_live():
        return _finish(cfg, "failed", error="Live key entered but environment is Test.")
    if secret.startswith("sk_test_") and cfg.is_live():
        return _finish(cfg, "failed", error="Test key entered but environment is Live.")
    try:
        import stripe
        stripe.api_key = secret
        acct = stripe.Account.retrieve()
        bal = stripe.Balance.retrieve()
        cur = (bal.get("available") or [{}])[0].get("currency", "") if bal else ""
        detail = "Account %s · %s · charges_enabled=%s" % (
            (acct.get("id") or "")[:12] + "…", (cur or cfg.currency or "?").upper(),
            acct.get("charges_enabled"))
        return _finish(cfg, "connected", detail=detail)
    except Exception as exc:
        return _finish(cfg, "failed", error=_safe_stripe_error(exc))


def _safe_stripe_error(exc):
    name = type(exc).__name__
    return {
        "AuthenticationError": "Invalid or revoked API key (401).",
        "PermissionError": "Key lacks the required permissions.",
        "RateLimitError": "Rate limited by Stripe (429).",
        "APIConnectionError": "Could not reach Stripe (network/timeout).",
    }.get(name, "Stripe check failed (%s)." % name)


def test_paypal(cfg):
    """Read-only PayPal check: fetch an OAuth token (client-credentials) + read app scopes.
    No order is created, no capture, no refund."""
    if not cfg.paypal_client_id or not cfg.has_secret("paypal_secret"):
        return _finish(cfg, "failed", error="Client id and secret are required.")
    secret = cfg.get_secret("paypal_secret")
    base = cfg.paypal_api_base or ("https://api-m.paypal.com" if cfg.is_live()
                                   else "https://api-m.sandbox.paypal.com")
    sandbox_base = "sandbox" in base
    if cfg.is_live() and sandbox_base:
        return _finish(cfg, "failed", error="Live environment but sandbox API base.")
    try:
        import requests
        resp = requests.post(f"{base}/v1/oauth2/token",
                             auth=(cfg.paypal_client_id, secret),
                             data={"grant_type": "client_credentials"},
                             headers={"Accept": "application/json"}, timeout=15)
        if resp.status_code in (401, 403):
            return _finish(cfg, "failed", error="Invalid client id/secret (%d)." % resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        scopes = (data.get("scope") or "").split()
        detail = "%s · token OK · %d scope(s)" % (
            "sandbox" if sandbox_base else "live", len(scopes))
        return _finish(cfg, "connected", detail=detail)
    except Exception:
        return _finish(cfg, "failed", error="Could not reach PayPal (network/timeout).")


def test_connection(cfg):
    return test_stripe(cfg) if cfg.provider == cfg.STRIPE else test_paypal(cfg)
