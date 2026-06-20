"""
Protected inbound endpoints for n8n → Django.

All endpoints require a valid `X-Signature` (HMAC-SHA256 of the raw body using
N8N_SHARED_SECRET). Payloads are validated; nothing sensitive is logged.
"""
from __future__ import annotations

import functools
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import events as ev
from .dispatcher import verify_signature
from .inbound import ingest_incoming_email
from .models import OutboundEvent, SupportMessage

logger = logging.getLogger("notifications")


def require_n8n_signature(view):
    @functools.wraps(view)
    def _wrapped(request, *args, **kwargs):
        secret = getattr(settings, "N8N_SHARED_SECRET", "") or ""
        signature = request.headers.get("X-Signature", "")
        if not verify_signature(secret, request.body, signature):
            return JsonResponse({"ok": False, "error": "invalid_signature"}, status=401)
        try:
            request.n8n_data = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
        return view(request, *args, **kwargs)

    return _wrapped


@csrf_exempt
@require_POST
@require_n8n_signature
def incoming_email(request):
    """n8n delivers a received email; we store it as a SupportMessage."""
    data = request.n8n_data
    if not (data.get("from_email") or data.get("from")):
        return JsonResponse({"ok": False, "error": "missing_sender"}, status=400)

    msg, created = ingest_incoming_email(data)

    # Optional auto-reply (n8n usually owns this, but we record the intent).
    if created and data.get("auto_reply") and msg.from_email and not msg.is_auto_replied:
        from .dispatcher import dispatch_event

        dispatch_event(
            ev.SUPPORT_AUTOREPLY,
            {"subject": msg.subject, "from_email": msg.from_email,
             "order_number": msg.order.order_number if msg.order else ""},
            recipient_email=msg.from_email,
            language=msg.language or "en",
        )
        msg.is_auto_replied = True
        msg.save(update_fields=["is_auto_replied"])

    return JsonResponse({
        "ok": True, "created": created, "id": msg.id,
        "linked_order": msg.order.order_number if msg.order else None,
        "linked_account": bool(msg.account),
    })


# Alias path used by some n8n setups.
support_message = incoming_email


@csrf_exempt
@require_POST
@require_n8n_signature
def email_status(request):
    """n8n reports the delivery result of an outbound email event."""
    data = request.n8n_data
    event_id = data.get("event_id")
    status = (data.get("status") or "").strip()
    if not event_id:
        return JsonResponse({"ok": False, "error": "missing_event_id"}, status=400)

    event = OutboundEvent.objects.filter(id=event_id).first()
    if not event:
        return JsonResponse({"ok": False, "error": "event_not_found"}, status=404)

    mapping = {
        "sent": OutboundEvent.STATUS_SENT,
        "delivered": OutboundEvent.STATUS_SENT,
        "failed": OutboundEvent.STATUS_FAILED,
        "bounced": OutboundEvent.STATUS_FAILED,
    }
    new_status = mapping.get(status.lower())
    if new_status:
        event.status = new_status
        if new_status == OutboundEvent.STATUS_SENT:
            event.dispatched_at = timezone.now()
        if data.get("error"):
            event.last_error = str(data["error"])[:2000]
        event.save(update_fields=["status", "dispatched_at", "last_error", "updated_at"])
    return JsonResponse({"ok": True, "status": event.status})


@csrf_exempt
@require_POST
@require_n8n_signature
def order_event(request):
    """
    n8n pushes an order-related event back into Django (e.g. a shipment update
    detected from the Printify mailbox). Updates tracking/status when present.
    """
    data = request.n8n_data
    from orders.models import Order

    order_number = data.get("order_number")
    order = Order.objects.filter(order_number=order_number).first() if order_number else None
    if not order:
        return JsonResponse({"ok": False, "error": "order_not_found"}, status=404)

    fields = []
    if data.get("tracking_number"):
        order.tracking_number = str(data["tracking_number"])[:128]
        fields.append("tracking_number")
    if data.get("tracking_url"):
        order.tracking_url = str(data["tracking_url"])[:200]
        fields.append("tracking_url")
    if data.get("carrier"):
        order.carrier = str(data["carrier"])[:64]
        fields.append("carrier")
    if data.get("printify_status"):
        order.printify_status = str(data["printify_status"])[:32]
        fields.append("printify_status")
    if fields:
        order.save(update_fields=fields + ["updated_at"])
    return JsonResponse({"ok": True, "updated": fields})
