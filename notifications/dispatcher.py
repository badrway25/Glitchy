"""
Django → n8n event dispatcher.

Every outbound automation/email event is recorded as an `OutboundEvent`, signed
with an HMAC-SHA256 shared secret, and POSTed to the configured n8n webhook.

Design rules (per project spec):
    * n8n is the PRIMARY channel for sending email.
    * SMTP is only a technical FALLBACK (used when n8n is disabled or a dispatch
      ultimately fails for an email-type event).
    * Secrets are never logged. We log status codes and truncated error strings.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

from .events import EVENT_CATALOG
from .models import OutboundEvent

logger = logging.getLogger("notifications")

# Events that result in a customer email (eligible for SMTP fallback).
_EMAIL_EVENTS = {
    "order.created", "order.paid", "order.in_production", "order.shipped",
    "order.tracking_available", "return.requested", "return.approved",
    "return.rejected", "refund.completed", "cart.abandoned",
    "newsletter.subscribed", "support.autoreply",
}


def compute_signature(secret: str, body: bytes) -> str:
    """HMAC-SHA256 hex digest of the raw request body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Constant-time verification for inbound n8n → Django calls."""
    if not secret or not signature:
        return False
    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, (signature or "").strip())


def _webhook_url(event_type: str) -> str:
    base = (getattr(settings, "N8N_WEBHOOK_BASE_URL", "") or "").rstrip("/")
    if not base:
        return ""
    # Path segment = event type with dots → hyphens (n8n-friendly).
    path = event_type.replace(".", "-")
    return f"{base}/{path}"


def _post_to_n8n(event: OutboundEvent) -> tuple[bool, int | None, str]:
    url = _webhook_url(event.event_type)
    if not url:
        return False, None, "N8N_WEBHOOK_BASE_URL not configured"

    body_dict = {
        "event": event.event_type,
        "language": event.language,
        "recipient": event.recipient_email,
        "data": event.payload,
    }
    body = json.dumps(body_dict, default=str, separators=(",", ":")).encode("utf-8")
    secret = getattr(settings, "N8N_SHARED_SECRET", "") or ""
    headers = {
        "Content-Type": "application/json",
        "X-Event-Type": event.event_type,
        # Application signature — observability / defense-in-depth (not the primary gate).
        "X-Signature": compute_signature(secret, body),
    }
    # PRIMARY auth: static shared header enforced by n8n native Header Auth.
    auth_name = getattr(settings, "N8N_HEADER_AUTH_NAME", "X-N8N-AUTH")
    auth_secret = getattr(settings, "N8N_HEADER_AUTH_SECRET", "") or ""
    if auth_secret:
        headers[auth_name] = auth_secret
    timeout = int(getattr(settings, "N8N_TIMEOUT", 15))
    try:
        resp = requests.post(url, data=body, headers=headers, timeout=timeout)
        if 200 <= resp.status_code < 300:
            return True, resp.status_code, ""
        return False, resp.status_code, f"HTTP {resp.status_code}"
    except requests.RequestException as exc:
        # Never include secrets/headers in the logged error.
        return False, None, f"{type(exc).__name__}: {exc}"


def _smtp_fallback(event: OutboundEvent) -> bool:
    """Render + send the email locally when n8n cannot deliver it."""
    if not getattr(settings, "EMAIL_SMTP_FALLBACK", True):
        return False
    if event.event_type not in _EMAIL_EVENTS or not event.recipient_email:
        return False
    try:
        from .emails import send_event_email_via_smtp

        return send_event_email_via_smtp(event)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("SMTP fallback failed for %s: %s", event.event_type, exc)
        return False


def dispatch_event(
    event_type: str,
    payload: dict,
    *,
    recipient_email: str = "",
    language: str = "en",
    order=None,
    return_request=None,
    dedupe: bool = False,
) -> OutboundEvent:
    """Create + dispatch an outbound event. Always returns a persisted record."""
    if dedupe and order is not None:
        # Idempotency: one customer email per (order, event) — reconciliation retries and
        # page refreshes must never double-send. A previously FAILED event may be retried.
        existing = (OutboundEvent.objects
                    .filter(order=order, event_type=event_type)
                    .exclude(status=OutboundEvent.STATUS_FAILED)
                    .first())
        if existing:
            return existing
    event = OutboundEvent.objects.create(
        event_type=event_type,
        recipient_email=recipient_email or "",
        language=language or "en",
        payload=payload or {},
        max_attempts=int(getattr(settings, "N8N_MAX_RETRIES", 3)),
        order=order,
        return_request=return_request,
    )
    return _try_dispatch(event)


def _try_dispatch(event: OutboundEvent) -> OutboundEvent:
    if not getattr(settings, "N8N_ENABLED", False):
        # n8n off: record as skipped, then attempt SMTP fallback so dev still
        # delivers transactional email.
        event.status = OutboundEvent.STATUS_SKIPPED
        if _smtp_fallback(event):
            event.status = OutboundEvent.STATUS_SENT
            event.last_error = "Delivered via SMTP fallback (n8n disabled)"
        event.save()
        return event

    ok, code, err = _post_to_n8n(event)
    event.attempts = (event.attempts or 0) + 1
    if ok:
        event.mark_sent(response_status=code)
    else:
        event.mark_failed(err, response_status=code)
        logger.warning("n8n dispatch failed event=%s status=%s", event.event_type, code)
        if event.status == OutboundEvent.STATUS_FAILED and _smtp_fallback(event):
            event.status = OutboundEvent.STATUS_SENT
            event.last_error = (event.last_error + " | recovered via SMTP fallback").strip(" |")
    event.save()
    return event


def resend_event(event: OutboundEvent) -> OutboundEvent:
    """Re-dispatch a previously failed/pending event (used by admin + command)."""
    event.status = OutboundEvent.STATUS_RETRYING
    event.save(update_fields=["status"])
    return _try_dispatch(event)


def retry_pending(limit: int = 50) -> int:
    """Retry failed/retrying events. Returns count re-sent successfully."""
    qs = OutboundEvent.objects.filter(
        status__in=[OutboundEvent.STATUS_FAILED, OutboundEvent.STATUS_RETRYING]
    ).order_by("created_at")[:limit]
    sent = 0
    for event in qs:
        if event.attempts >= event.max_attempts:
            continue
        resend_event(event)
        if event.status == OutboundEvent.STATUS_SENT:
            sent += 1
    return sent
