"""
Transactional email rendering for the SMTP fallback path.

n8n is the primary sender; when it is unavailable we render the SAME structured
payload into a branded HTML email and send it via Django's SMTP backend.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

# event_type -> (subject template, body intro paragraph, optional CTA label)
EVENT_TEMPLATES = {
    "order.created": ("Order confirmed", "order"),
    "order.paid": ("Payment received", "order"),
    "order.in_production": ("Your order is in production", "order"),
    "order.shipped": ("Your order has shipped", "order"),
    "order.tracking_available": ("Your tracking is ready", "order"),
    "return.requested": ("We received your return request", "return"),
    "return.approved": ("Your return has been approved", "return"),
    "return.rejected": ("Update on your return request", "return"),
    "refund.completed": ("Your refund is complete", "return"),
    "cart.abandoned": ("You left something behind", "cart"),
    "newsletter.subscribed": ("Welcome to the club", "newsletter"),
    "support.autoreply": ("We received your message", "support"),
}


def _subject_for(event) -> str:
    base = getattr(settings, "SITE_NAME", "Glitchy")
    mapping = {
        "order.created": _("Order confirmed"),
        "order.paid": _("Payment received"),
        "order.in_production": _("Your order is in production"),
        "order.shipped": _("Your order has shipped"),
        "order.tracking_available": _("Your tracking is ready"),
        "return.requested": _("We received your return request"),
        "return.approved": _("Your return has been approved"),
        "return.rejected": _("Update on your return request"),
        "refund.completed": _("Your refund is complete"),
        "cart.abandoned": _("You left something behind"),
        "newsletter.subscribed": _("Welcome to %(brand)s") % {"brand": base},
        "support.autoreply": _("We received your message"),
    }
    subject = mapping.get(event.event_type, _("Update from %(brand)s") % {"brand": base})
    payload = event.payload or {}
    if payload.get("order_number"):
        return f"{subject} • #{payload['order_number']}"
    return f"{subject} • {base}"


def render_event_email(event) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for an event, in its language."""
    lang = event.language or "en"
    kind = EVENT_TEMPLATES.get(event.event_type, ("Update", "generic"))[1]
    with translation.override(lang):
        subject = _subject_for(event)
        context = {
            "event": event,
            "kind": kind,
            "data": event.payload or {},
            "SITE_NAME": getattr(settings, "SITE_NAME", "Glitchy"),
            "SITE_BASE_URL": getattr(settings, "SITE_BASE_URL", ""),
            "RETURN_WINDOW_DAYS": getattr(settings, "RETURN_WINDOW_DAYS", 14),
            "CURRENCY_SYMBOL": getattr(settings, "STORE_CURRENCY_SYMBOL", "€"),
        }
        html = render_to_string("notifications/email/transactional.html", context)
    text = strip_tags(html)
    return subject, html, text


def send_event_email_via_smtp(event) -> bool:
    if not event.recipient_email:
        return False
    subject, html, text = render_event_email(event)
    # From / Reply-To / transport are resolved from the admin Mail Control Center,
    # falling back to settings. get_email_backend_settings() returns {} when no DB
    # config is active, so get_connection() then yields the DEFAULT connection —
    # unchanged behaviour (and the locmem test still works).
    from .email_settings import (get_connection, get_default_from_email,
                                 get_reply_to_email)
    reply_to = get_reply_to_email()
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=get_default_from_email() or getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[event.recipient_email],
        reply_to=[reply_to] if reply_to else None,
        connection=get_connection(),
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)
    return True
