"""The public contact form: validation, anti-abuse and delivery.

Design rules:

* **Store first, dispatch second.** The customer's message lands in the database
  before we try n8n/SMTP, so an outage never loses it — the row stays `pending`
  and is retryable from the admin.
* **Anti-abuse mirrors checkout** (the pattern already proven in this codebase):
  a honeypot field, a signed minimum-fill-time token, and a per-session rate
  limit. Bots get a normal-looking success page and nothing is stored.
* **No secrets, no surprises**: we never echo the message back into logs and we
  never send anything the customer did not press send on.
"""
from __future__ import annotations

import hashlib
import time

from django.conf import settings
from django.core import signing
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .dispatcher import dispatch_event
from .events import INTERNAL_ALERT
from .models import ContactRequest

TS_SALT = "contact-ts"
MIN_FILL_SECONDS = 3
MAX_TOKEN_AGE = 60 * 60 * 4
RATE_LIMIT = 5
RATE_WINDOW = 3600
MIN_MESSAGE_CHARS = 12
MAX_MESSAGE_CHARS = 4000
#: a resend inside this window is the same request, outside it is a follow-up
DEDUPE_WINDOW_SECONDS = 15 * 60

VALID_CATEGORIES = {value for value, _label in ContactRequest.CATEGORY_CHOICES}


def new_form_token() -> str:
    return signing.dumps(time.time(), salt=TS_SALT)


def _rate_limited(request, *, count=True) -> bool:
    """Sliding window over the session AND a salted IP fingerprint.

    Session-only limiting is trivially bypassed by dropping the cookie, so the
    request IP (hashed, never stored raw) carries a cache-backed counter too.
    `count=False` only *checks* the budget — a rejected form must not consume it,
    or a few typos would lock a genuine customer out for an hour."""
    now = time.time()
    limited = False
    key = "_contact_hits"
    try:
        hits = [t for t in request.session.get(key, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            limited = True
        elif count:
            hits.append(now)
            request.session[key] = hits
            request.session.modified = True
    except Exception:
        pass

    try:
        from django.core.cache import cache
        ip_key = "contact_rl:" + _ip_fingerprint(request)
        ip_hits = [t for t in (cache.get(ip_key) or []) if now - t < RATE_WINDOW]
        if len(ip_hits) >= RATE_LIMIT * 2:      # a shared NAT needs more headroom
            limited = True
        elif count:
            ip_hits.append(now)
            cache.set(ip_key, ip_hits, RATE_WINDOW)
    except Exception:
        pass                                     # cache down -> fail open, never 500
    return limited


def _ip_fingerprint(request) -> str:
    """Salted hash of the client IP — enough to rate-limit, never stored raw."""
    from django.conf import settings as dj_settings
    salt = (getattr(dj_settings, "SECRET_KEY", "") or "")[:16]
    ip = request.META.get("REMOTE_ADDR", "") or ""
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()[:24]


def _fingerprint(email: str, category: str, message: str) -> str:
    raw = f"{email.lower()}|{category}|{message.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ContactSubmission:
    """Result of handling a POST: what to tell the user, and what happened."""

    def __init__(self, *, ok, errors=None, request_obj=None, silent=False):
        self.ok = ok
        self.errors = errors or {}
        self.request_obj = request_obj
        self.silent = silent            # bot: pretend success, store nothing


def handle_submission(request) -> ContactSubmission:
    post = request.POST

    # --- layer 1: honeypot (bots fill hidden fields) -------------------------
    if (post.get("website") or "").strip():
        return ContactSubmission(ok=True, silent=True)

    # --- layer 2: minimum fill time, signed so it cannot be forged -----------
    # Only a SUSPICIOUSLY FAST submit is treated as a bot. An expired or missing
    # token means a real person left the tab open (or reloaded oddly) — telling
    # them to send again is honest; silently binning their message is not.
    try:
        started = signing.loads(post.get("form_ts") or "", salt=TS_SALT,
                                max_age=MAX_TOKEN_AGE)
    except signing.SignatureExpired:
        return ContactSubmission(ok=False, errors={
            "form": _("This form was open for a while. Please send it again — "
                      "your message is still here.")})
    except Exception:
        return ContactSubmission(ok=True, silent=True)
    try:
        too_fast = time.time() - float(started) < MIN_FILL_SECONDS
    except (TypeError, ValueError):
        too_fast = False
    if too_fast:
        return ContactSubmission(ok=True, silent=True)

    # --- layer 3: rate limit (checked now, counted only on success) ----------
    if _rate_limited(request, count=False):
        return ContactSubmission(ok=False, errors={
            "form": _("You've sent several messages already. Please give us a "
                      "little time to reply.")})

    # --- validation ----------------------------------------------------------
    errors = {}
    name = (post.get("name") or "").strip()[:120]
    email = (post.get("email") or "").strip()[:254]
    category = (post.get("category") or "").strip()
    order_number = (post.get("order_number") or "").strip()[:40]
    message = (post.get("message") or "").strip()[:MAX_MESSAGE_CHARS]

    if not name:
        errors["name"] = _("Please tell us your name.")
    try:
        validate_email(email)
    except ValidationError:
        errors["email"] = _("Please enter a valid email address so we can reply.")
    if category not in VALID_CATEGORIES:
        errors["category"] = _("Please choose what your message is about.")
    if len(message) < MIN_MESSAGE_CHARS:
        errors["message"] = _("Please add a little more detail so we can help.")
    if not post.get("consent"):
        errors["consent"] = _("Please accept the privacy notice so we may reply.")
    if errors:
        return ContactSubmission(ok=False, errors=errors)

    # --- idempotency: a double-click is one request, a follow-up is not ------
    # Scoped to a short window: an identical message sent days later (a chase-up,
    # or a retry after we failed to deliver the first one) is a NEW request.
    from django.utils import timezone as tz
    fingerprint = _fingerprint(email, category, message)
    cutoff = tz.now() - tz.timedelta(seconds=DEDUPE_WINDOW_SECONDS)
    existing = (ContactRequest.objects
                .filter(fingerprint=fingerprint, created_at__gte=cutoff)
                .exclude(status=ContactRequest.STATUS_FAILED)
                .first())
    if existing is not None:
        return ContactSubmission(ok=True, request_obj=existing)

    from django.utils import translation
    contact = ContactRequest.objects.create(
        name=name, email=email, category=category, order_number=order_number,
        message=message, language=(translation.get_language() or "en")[:5],
        fingerprint=fingerprint,
        account=request.user if getattr(request.user, "is_authenticated", False) else None,
    )
    _rate_limited(request)          # only an accepted message consumes budget
    _link_order(contact)
    _dispatch(contact)
    return ContactSubmission(ok=True, request_obj=contact)


def _link_order(contact) -> None:
    """Attach the order when the customer quoted a real order number."""
    if not contact.order_number:
        return
    try:
        from orders.models import Order
        order = Order.objects.filter(order_number=contact.order_number).first()
        if order is not None:
            contact.order = order
            contact.save(update_fields=["order"])
    except Exception:
        pass


def _notify_recipient() -> str:
    """Admin-notify address (Mail Control Center → env)."""
    try:
        from .email_settings import get_admin_notify_email
        return get_admin_notify_email()
    except Exception:
        return (getattr(settings, "ADMIN_NOTIFY_EMAIL", "")
                or getattr(settings, "SUPPORT_EMAIL", ""))


def _dispatch(contact) -> None:
    """Queue the notification. A failure never breaks the customer's journey —
    the stored row simply stays `pending` for a retry."""
    try:
        event = dispatch_event(
            INTERNAL_ALERT,
            {
                "subject": f"Contact: {contact.get_category_display()}",
                "category": contact.category,
                "name": contact.name,
                "reply_to": contact.email,
                "order_number": contact.order_number,
                "message": contact.message,
                "language": contact.language,
            },
            recipient_email=_notify_recipient(),
            language=contact.language,
        )
    except Exception:
        contact.status = ContactRequest.STATUS_PENDING
        contact.save(update_fields=["status"])
        return

    # Only link a real outbox row: the message is already safely stored, and an
    # unexpected return value must never turn into a 500 after the customer
    # pressed send.
    from .models import OutboundEvent
    fields = ["status"]
    if isinstance(event, OutboundEvent):
        contact.event = event
        fields.append("event")
    contact.status = (ContactRequest.STATUS_SENT
                      if getattr(event, "status", "") == "sent"
                      else ContactRequest.STATUS_PENDING)
    contact.save(update_fields=fields)
