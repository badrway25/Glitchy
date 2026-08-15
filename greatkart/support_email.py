"""Support-email configuration guardrails (F5).

`SUPPORT_EMAIL`, `DEFAULT_FROM_EMAIL` and friends fall back to `*.example.com`
placeholders when the production env doesn't set them (see settings.py). Two rules
follow from that:

* nothing customer-facing may ever show a placeholder address, and
* the assistant must route shoppers to the contact form instead of quoting one.

This module centralises the "is this a real, configured address?" check so the
assistant, the notifications layer and a Django system check all agree. It reads
settings only — it never prints or logs the value.
"""
from __future__ import annotations

from django.conf import settings

#: domains reserved for documentation/examples (RFC 2606) — never real inboxes.
PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "example.edu")


def _clean(value) -> str:
    return (value or "").strip()


def is_placeholder_email(value) -> bool:
    """True for empty, malformed, or reserved-example-domain addresses."""
    v = _clean(value).lower()
    if not v or "@" not in v:
        return True
    return v.rsplit("@", 1)[-1] in PLACEHOLDER_DOMAINS


def support_email() -> str:
    return _clean(getattr(settings, "SUPPORT_EMAIL", ""))


def support_email_configured() -> bool:
    """True only when SUPPORT_EMAIL is a real, non-placeholder address."""
    return not is_placeholder_email(support_email())


def public_support_email() -> str:
    """The address safe to show a customer — '' when it is a placeholder.

    Callers should fall back to the /contact/ form when this returns ''."""
    email = support_email()
    return "" if is_placeholder_email(email) else email
