"""
High-level notification helpers.

These build the canonical structured payload from domain objects (Order,
ReturnRequest) and hand it to the dispatcher. Both the n8n path and the SMTP
fallback consume the exact same payload shape.
"""
from __future__ import annotations

from django.conf import settings
from django.urls import reverse

from . import events as ev
from .dispatcher import dispatch_event


def _abs(path: str) -> str:
    base = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def _variant_label(order_product) -> str:
    parts = []
    for v in order_product.variations.all():
        parts.append(f"{v.variation_category.title()}: {v.variation_value}")
    return ", ".join(parts)


def build_order_payload(order) -> dict:
    items = []
    for op in order.orderproduct_set.all():
        items.append({
            "name": op.product.product_name,
            "variant": _variant_label(op),
            "qty": op.quantity,
            "unit_price": round(float(op.product_price), 2),
            "line_total": round(op.line_total(), 2),
        })
    payload = {
        "order_number": order.order_number,
        "first_name": order.first_name,
        "email": order.email,
        "currency": order.currency,
        "items": items,
        "items_subtotal": round(float(order.items_subtotal or 0), 2),
        "shipping_cost": round(float(order.shipping_cost or 0), 2),
        "tax": round(float(order.tax or 0), 2),
        "order_total": round(float(order.order_total or 0), 2),
        "shipping": {
            "country": order.shipping_country or order.country,
            "min_days": order.shipping_min_days,
            "max_days": order.shipping_max_days,
        },
        "address": {
            "line1": order.address_line_1,
            "line2": order.address_line_2,
            "city": order.city,
            "state": order.state,
            "postal_code": order.postal_code,
            "country": order.country,
        },
    }
    if order.tracking_url:
        payload["tracking_url"] = order.tracking_url
    if order.tracking_number:
        payload["tracking_number"] = order.tracking_number
    return payload


def notify_order_event(order, event_type) -> None:
    dispatch_event(
        event_type,
        build_order_payload(order),
        recipient_email=order.email,
        language=order.language_code or "en",
        order=order,
        dedupe=True,   # one customer email per (order, event) — idempotent by design
    )


def build_return_payload(return_request) -> dict:
    order = return_request.order
    return {
        "order_number": order.order_number,
        "first_name": order.first_name,
        "status": return_request.status,
        "refund_amount": round(float(return_request.refund_amount or 0), 2),
        "currency": order.currency,
        "reason": return_request.reason,
        "admin_note": return_request.admin_note,
        "return_url": _abs(reverse("returns:status", args=[return_request.public_token])),
    }


def notify_return_event(return_request, event_type) -> None:
    order = return_request.order
    dispatch_event(
        event_type,
        build_return_payload(return_request),
        recipient_email=return_request.customer_email or order.email,
        language=order.language_code or "en",
        order=order,
        return_request=return_request,
    )


def notify_internal(event_type, *, subject: str, order=None, extra: dict | None = None) -> None:
    payload = {"subject": subject}
    if order is not None:
        payload["order_number"] = order.order_number
    if extra:
        payload.update(extra)
    dispatch_event(
        event_type,
        payload,
        recipient_email=getattr(settings, "ADMIN_NOTIFY_EMAIL", "") or "",
        language="en",
        order=order,
    )


def notify_printify_error(order, error: str) -> None:
    notify_internal(
        ev.PRINTIFY_ERROR,
        subject=f"Printify error on order {getattr(order, 'order_number', '?')}",
        order=order,
        extra={"error": str(error)[:1000]},
    )


def notify_negative_margin(order) -> None:
    m = order.margins()
    if m.net_margin < 0:
        notify_internal(
            ev.MARGIN_NEGATIVE,
            subject=f"Negative margin on order {order.order_number}",
            order=order,
            extra={"net_margin": m.net_margin, "currency": m.currency},
        )
