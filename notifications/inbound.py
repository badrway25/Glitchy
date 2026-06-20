"""
Inbound processing for messages synced from n8n (received emails / support).

Pure-ish helpers so the API layer stays thin and the logic stays testable.
"""
from __future__ import annotations

import re

from django.contrib.auth import get_user_model

from orders.models import Order
from .models import SupportMessage

Account = get_user_model()

# Order numbers in this project look like YYYYMMDD<id> (>= 9 digits) and are
# often referenced as "#20250131123" or "order 20250131123".
_ORDER_RE = re.compile(r"#?\b(\d{9,20})\b")


def find_order(subject: str, body: str):
    haystack = f"{subject or ''} {body or ''}"
    for match in _ORDER_RE.findall(haystack):
        order = Order.objects.filter(order_number=match).first()
        if order:
            return order
    return None


def find_account(email: str):
    if not email:
        return None
    return Account.objects.filter(email__iexact=email.strip()).first()


def ingest_incoming_email(payload: dict) -> tuple[SupportMessage, bool]:
    """
    Create (or return existing) SupportMessage from an n8n payload.

    Deduplicates on `message_id`. Returns (message, created).
    """
    message_id = (payload.get("message_id") or "").strip()
    if message_id:
        existing = SupportMessage.objects.filter(message_id=message_id).first()
        if existing:
            return existing, False

    from_email = (payload.get("from_email") or payload.get("from") or "").strip()
    subject = (payload.get("subject") or "").strip()[:255]
    body_text = payload.get("body_text") or payload.get("text") or ""
    body_html = payload.get("body_html") or payload.get("html") or ""

    order = find_order(subject, body_text)
    account = find_account(from_email)

    msg = SupportMessage.objects.create(
        from_email=from_email,
        to_email=(payload.get("to_email") or payload.get("to") or "").strip(),
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        language=(payload.get("language") or "").strip()[:5],
        message_id=message_id,
        thread_id=(payload.get("thread_id") or "").strip()[:255],
        attachments_meta=payload.get("attachments") or [],
        order=order,
        account=account,
    )
    return msg, True
