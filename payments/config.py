"""Credential resolver — DB-preferred, ENV-fallback, safety-gated.

Backward-compatible on purpose: every getter returns the admin DB config value only when a
provider row is ENABLED and actually holds the secret; otherwise it falls back to today's
``settings.*`` env values. So checkout behaves EXACTLY as before until an owner enters a key in
the admin. Live keys additionally require the explicit live-mode gate.
"""
from django.conf import settings


def _cfg(provider):
    try:
        from .models import PaymentProviderConfig
        return PaymentProviderConfig.for_provider(provider)
    except Exception:
        return None


def _use_db(cfg, secret_name=None):
    if not (cfg and cfg.is_enabled):
        return False
    if cfg.is_live() and not cfg.allow_live_mode:
        return False        # never serve a live key unless the live gate is on
    if secret_name and not cfg.has_secret(secret_name):
        return False
    return True


# -- Stripe ---------------------------------------------------------------
def stripe_secret_key():
    c = _cfg("stripe")
    if _use_db(c, "stripe_secret_key"):
        s = c.get_secret("stripe_secret_key")
        if s:
            return s
    return getattr(settings, "STRIPE_SECRET_KEY", "")


def stripe_webhook_secret():
    c = _cfg("stripe")
    if _use_db(c, "stripe_webhook_secret"):
        s = c.get_secret("stripe_webhook_secret")
        if s:
            return s
    return getattr(settings, "STRIPE_WEBHOOK_SECRET", "")


def stripe_publishable_key():
    c = _cfg("stripe")
    if _use_db(c) and c.stripe_publishable_key:
        return c.stripe_publishable_key
    return getattr(settings, "STRIPE_PUBLIC_KEY", "")


def stripe_source():
    return "db" if _use_db(_cfg("stripe"), "stripe_secret_key") else "env"


# -- PayPal ---------------------------------------------------------------
def paypal_client_id():
    c = _cfg("paypal")
    if _use_db(c) and c.paypal_client_id:
        return c.paypal_client_id
    return getattr(settings, "PAYPAL_CLIENT_ID", "")


def paypal_secret():
    c = _cfg("paypal")
    if _use_db(c, "paypal_secret"):
        s = c.get_secret("paypal_secret")
        if s:
            return s
    return getattr(settings, "PAYPAL_SECRET", "")


def paypal_api_base():
    c = _cfg("paypal")
    if _use_db(c) and c.paypal_api_base:
        return c.paypal_api_base
    # env default (sandbox unless overridden)
    return getattr(settings, "PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")


def paypal_source():
    return "db" if _use_db(_cfg("paypal"), "paypal_secret") else "env"


def paypal_available():
    """Fail-closed availability. True when either an admin config is enabled + checkout-ready,
    or the legacy env gate (PAYPAL_ENABLED + client id + secret) is satisfied."""
    c = _cfg("paypal")
    if c and c.is_ready_for_checkout():
        return True
    return bool(getattr(settings, "PAYPAL_ENABLED", False)
                and getattr(settings, "PAYPAL_CLIENT_ID", "")
                and getattr(settings, "PAYPAL_SECRET", ""))
