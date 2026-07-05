import logging
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings

from carts.models import CartItem
from store.models import Product
from accounts.models import Address

from .forms import OrderForm
from .models import Order, Payment, OrderProduct
from .services import finalize_order_payment

import datetime
import json


import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY   # import-time default; refreshed per request below


def _use_stripe():
    """Refresh the Stripe key per request from the admin config (DB-preferred) or env, so a key
    entered in the Payment Control Center takes effect without a redeploy. Backward-compatible:
    with no DB config it returns the same env key as before."""
    from payments import config as pconf
    stripe.api_key = pconf.stripe_secret_key() or ""
    return stripe


def _resolve_pending_order(request, order_number):
    """Find the pending order for the current actor (authed user OR guest session)."""
    qs = Order.objects.filter(order_number=order_number, is_ordered=False)
    if request.user.is_authenticated:
        order = qs.filter(user=request.user).first()
        if order:
            return order
    session_key = request.session.session_key
    if session_key:
        return qs.filter(is_guest=True, session_key=session_key).first()
    return None


def _make_payment(order, intent):
    """Idempotent Payment creation that works for guests (user may be None)."""
    payment, _created = Payment.objects.get_or_create(
        payment_id=intent.id,
        defaults={
            "user": order.user,
            "email": order.email,
            "payment_method": "Stripe",
            "amount_paid": str(order.order_total),
            "status": intent.status,
        },
    )
    return payment


def stripe_return(request):
    payment_intent_id = request.GET.get("payment_intent")
    if not payment_intent_id:
        messages.error(request, "Missing payment reference. Please try again.")
        return redirect("checkout")

    # retrieve PI from Stripe
    try:
        _use_stripe()
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except Exception:
        messages.error(request, "We couldn't verify the payment with Stripe. Please try again.")
        return redirect("checkout")

    order_number = (intent.get("metadata") or {}).get("order_number")
    if not order_number:
        messages.error(request, "Could not verify your order. Please try again.")
        return redirect("checkout")

    # find pending order
    order = _resolve_pending_order(request, order_number)
    if not order:
        messages.error(request, "Order not found or already confirmed.")
        return redirect("checkout")

    if intent.status != "succeeded":
        messages.error(request, f"Payment not completed (status: {intent.status}).")
        return redirect("payments")

    payment = _make_payment(order, intent)

    # finalize only if not already ordered
    if not order.is_ordered:
        try:
            finalize_order_payment(order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return redirect("home")

    messages.success(request, "Payment successful. Your order is confirmed.")
    return redirect(f"{reverse('order_complete')}?order_number={order.order_number}&payment_id={payment.payment_id}")


@require_POST
def paypal_create_order(request):
    """Server-side PayPal order creation from the checkout snapshot (pending Order + cart).

    Replaces the old client-side actions.order.create({amount only}) that made the popup
    show wallet defaults and context-free totals. Sandbox/live comes from the resolver;
    amounts are Decimal-built and consistency-checked before anything reaches PayPal."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    order = _resolve_pending_order(request, body.get("order_number"))
    if not order:
        return JsonResponse({"error": str(_("Order not found."))}, status=404)

    cart_items, _sk = _place_order_cart_items(request)
    if not cart_items:
        return JsonResponse({"error": str(_("Your cart is empty."))}, status=400)

    # the popup must show the checkout address — refuse to open it without one
    if not (order.address_line_1 and order.city and order.country):
        return JsonResponse({"error": str(
            _("Please complete your delivery address before paying with PayPal."))}, status=400)

    from payments.paypal_payload import PayloadMismatch, build_order_payload
    try:
        payload = build_order_payload(order, cart_items)
    except PayloadMismatch as exc:
        logger.warning("paypal payload mismatch for order %s: %s", order.order_number, exc)
        return JsonResponse({"error": str(
            _("Payment amount mismatch prevented for your safety. Please refresh and try "
              "again."))}, status=409)

    from .paypal import create_order
    paypal_id, err = create_order(payload)
    if not paypal_id:
        if err in ("SHIPPING_ADDRESS_INVALID", "INVALID_COUNTRY_CODE", "POSTAL_CODE_REQUIRED"):
            msg = _("PayPal could not validate the provided shipping address. Please review "
                    "it and choose PayPal again.")
        elif err == "paypal_unavailable":
            msg = _("PayPal is temporarily unavailable. Please use card.")
        else:
            msg = _("PayPal order could not be created. Please try again or use card.")
        return JsonResponse({"error": str(msg), "code": err}, status=502)
    return JsonResponse({"id": paypal_id})


def _paypal_success_payload(order, payment_id, status="completed"):
    """Stable success contract the JS relies on — ok/status/redirect_url, no PII."""
    from django.urls import reverse
    redirect_url = (reverse("order_complete")
                    + f"?order_number={order.order_number}&payment_id={payment_id}")
    return {"ok": True, "status": status, "order_id": order.order_number,
            "payment_id": payment_id, "redirect_url": redirect_url}


@require_POST
def paypal_capture(request):
    """SERVER-SIDE capture + finalize for PayPal, with a deterministic JSON contract.

    ok/status/redirect_url always; already-completed orders answer an IDEMPOTENT success
    (no second capture, ever); ORDER_ALREADY_CAPTURED from PayPal reconciles from the DB.
    Amount+currency verified from the capture response. Logs only provider/op/status codes."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "status": "error", "code": "BAD_JSON",
                             "message": "Invalid JSON"}, status=400)

    order_number = body.get("order_number")
    # IDEMPOTENCY FIRST: if this order is already paid, this is a success — never a retry,
    # never a scary message, never a second capture.
    completed = Order.objects.filter(order_number=order_number, is_ordered=True).first()
    if completed and (request.user.is_authenticated and completed.user_id == request.user.id
                      or completed.session_key == request.session.session_key):
        pid = completed.payment.payment_id if completed.payment_id else ""
        return JsonResponse(_paypal_success_payload(completed, pid, "already_completed"))

    order = _resolve_pending_order(request, order_number)
    if not order:
        return JsonResponse({"ok": False, "status": "error", "code": "ORDER_NOT_FOUND",
                             "message": str(_("Order not found or already confirmed."))},
                            status=404)

    from .paypal import capture_order
    result, issue = capture_order(body.get("paypal_order_id"))
    if result is None:
        if issue == "INSTRUMENT_DECLINED":
            return JsonResponse({"ok": False, "status": "error", "code": issue, "retry": True,
                                 "message": str(_("Your payment method was declined inside "
                                                  "PayPal. Please try another one."))}, status=402)
        if issue == "ORDER_ALREADY_CAPTURED":
            if order.is_ordered and order.payment_id:
                return JsonResponse(_paypal_success_payload(
                    order, order.payment.payment_id, "already_completed"))
            logger.warning("paypal op=capture order=%s already-captured but not finalized",
                           order.order_number)
            return JsonResponse({"ok": False, "status": "error", "code": issue,
                                 "message": str(_("Do not pay again until we check this "
                                                  "order. Please contact us."))}, status=409)
        logger.warning("paypal op=capture order=%s failed issue=%s", order.order_number, issue)
        return JsonResponse({"ok": False, "status": "error", "code": "PAYPAL_CAPTURE_FAILED",
                             "message": str(_("PayPal could not confirm the payment. Please "
                                              "try again or use card."))}, status=502)

    status = result.get("status", "")
    if status != "COMPLETED":
        logger.warning("paypal op=capture order=%s status=%s", order.order_number, status or "?")
        if status == "PENDING":
            return JsonResponse({"ok": True, "status": "pending",
                                 "message": str(_("Your PayPal payment is pending review. We "
                                                  "will confirm it by email shortly."))})
        return JsonResponse({"ok": False, "status": "error",
                             "code": "PAYPAL_STATUS_" + (status or "UNKNOWN"),
                             "message": str(_("PayPal could not confirm the payment. Please "
                                              "try again or use card."))}, status=402)

    expected = f"{float(order.order_total):.2f}"
    currency = (getattr(settings, "PAYPAL_CURRENCY", "EUR") or "EUR").upper()
    if result.get("amount") != expected or (result.get("currency") or "").upper() != currency:
        logger.error("paypal op=capture order=%s amount_mismatch got=%s/%s want=%s/%s",
                     order.order_number, result.get("amount"), result.get("currency"),
                     expected, currency)
        return JsonResponse({"ok": False, "status": "error", "code": "AMOUNT_MISMATCH",
                             "message": str(_("Payment amount mismatch prevented for your "
                                              "safety. Please contact support."))}, status=409)

    trans_id = result.get("capture_id") or body.get("paypal_order_id")
    payment, _created = Payment.objects.get_or_create(
        payment_id=trans_id,
        defaults={"user": order.user, "email": order.email, "payment_method": "PayPal",
                  "amount_paid": str(order.order_total), "status": "COMPLETED"})
    if not order.is_ordered:
        try:
            finalize_order_payment(order=order, payment=payment)
        except Exception:
            logger.error("paypal op=finalize order=%s failed", order.order_number)
            return JsonResponse({"ok": False, "status": "error", "code": "FINALIZE_FAILED",
                                 "message": str(_("Payment succeeded, but we could not "
                                                  "finalize your order. Please contact "
                                                  "support."))}, status=500)
    messages.success(request, _("Payment successful. Your order is confirmed."))
    return JsonResponse(_paypal_success_payload(order, payment.payment_id, "completed"))


@require_POST
def paypal_status(request):
    """Post-timeout reconciliation — DB-only read, idempotent, never captures.

    If the capture finished server-side after the frontend gave up, this answers
    completed + redirect so a PAID customer reaches the thank-you page instead of being
    told to contact support."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "status": "error"}, status=400)
    order_number = (body.get("order_number") or "")[:40]
    qs = Order.objects.filter(order_number=order_number)
    if request.user.is_authenticated:
        order = qs.filter(user=request.user).first()
    else:
        order = qs.filter(is_guest=True, session_key=request.session.session_key).first()
    if not order:
        return JsonResponse({"ok": True, "status": "unknown"})
    if order.is_ordered and order.payment_id:
        return JsonResponse(_paypal_success_payload(
            order, order.payment.payment_id, "completed"))
    return JsonResponse({"ok": True, "status": "processing"})


@require_POST
def stripe_create_intent(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_number = data.get("order_number")
    if not order_number:
        return JsonResponse({"error": "Missing order_number"}, status=400)

    order = _resolve_pending_order(request, order_number)
    if not order:
        return JsonResponse({"error": "Order not found"}, status=404)

    try:
        amount_cents = int(round(float(order.order_total) * 100))
    except Exception:
        return JsonResponse({"error": "Invalid order total"}, status=400)

    if amount_cents <= 0:
        return JsonResponse({"error": str(_("Invalid order total."))}, status=400)

    # Config first: an unconfigured Stripe must read as a clear service message, not a crash.
    from payments import config as pconf
    if not pconf.stripe_secret_key():
        logger.warning("stripe intent refused: no secret key configured (db+env empty)")
        return JsonResponse({"error": str(
            _("Card payments are not configured yet. Please choose another payment method "
              "or contact us."))}, status=503)

    try:
        _use_stripe()
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=settings.STRIPE_CURRENCY,
            metadata={
                "order_number": order.order_number,
                "user_id": str(order.user_id or "guest"),
            },
            receipt_email=order.email or None,
            automatic_payment_methods={"enabled": True},
        )
    except Exception as exc:
        # Safe diagnostics: error class + Stripe code only — never the key, never PII.
        code = getattr(exc, "code", "") or getattr(getattr(exc, "error", None), "code", "") or ""
        logger.error("stripe intent creation failed: %s code=%s order=%s",
                     type(exc).__name__, code, order.order_number)
        return JsonResponse({"error": str(
            _("We could not start the card payment. Please try again in a moment or choose "
              "another payment method."))}, status=502)

    from payments import config as pconf
    return JsonResponse({
        "clientSecret": intent.client_secret,
        "publishableKey": pconf.stripe_publishable_key(),
    })


@require_POST
def stripe_confirm(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        messages.error(request, "Invalid payment confirmation payload.")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_number = data.get("order_number")
    payment_intent_id = data.get("payment_intent_id")

    if not order_number or not payment_intent_id:
        messages.error(request, "Payment data missing. Please try again.")
        return JsonResponse({"error": "missing_fields"}, status=400)

    order = _resolve_pending_order(request, order_number)
    if not order:
        messages.error(request, "Order not found or already confirmed.")
        return JsonResponse({"error": "order_not_found"}, status=404)

    # verify with Stripe
    try:
        _use_stripe()
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except Exception:
        messages.error(request, "We couldn't verify the payment with Stripe.")
        return JsonResponse({"error": "stripe_retrieve_failed"}, status=500)

    if intent.status != "succeeded":
        messages.error(request, f"Payment not completed (status: {intent.status}).")
        return JsonResponse({"error": f"Payment not succeeded ({intent.status})"}, status=400)

    payment = _make_payment(order, intent)

    # finalize only if needed
    if not order.is_ordered:
        try:
            finalize_order_payment(order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return JsonResponse({"error": "finalize_failed"}, status=500)

    messages.success(request, "Payment successful. Your order is confirmed.")
    return JsonResponse({
        "order_number": order.order_number,
        "transID": payment.payment_id,
    })


def _ev_get(obj, key, default=None):
    """Access a field on a Stripe object OR a plain dict (for tests)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Signature-verified Stripe webhook. Idempotently finalizes orders and records
    refunds server-side, then lets the notifications layer fire order.paid.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    from payments import config as pconf
    from payments.models import PaymentEvent
    _use_stripe()
    secret = pconf.stripe_webhook_secret()

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        # Invalid signature / payload — reject (no secret logged).
        PaymentEvent.log("stripe", PaymentEvent.KIND_WEBHOOK, ok=False, reason_safe="signature/payload rejected")
        return HttpResponse(status=400)

    etype = _ev_get(event, "type")
    obj = (_ev_get(event, "data") or {}).get("object") if isinstance(_ev_get(event, "data"), dict) \
        else _ev_get(_ev_get(event, "data"), "object")
    obj = obj or {}

    from .services import apply_stripe_refund, finalize_from_intent

    try:
        if etype in ("payment_intent.succeeded", "checkout.session.completed"):
            meta = dict(_ev_get(obj, "metadata") or {})
            order_number = meta.get("order_number")
            if order_number:
                # checkout.session uses amount_total; payment_intent uses amount
                amount_cents = _ev_get(obj, "amount") or _ev_get(obj, "amount_total")
                amount = round(float(amount_cents) / 100.0, 2) if amount_cents else None
                intent_id = _ev_get(obj, "payment_intent") or _ev_get(obj, "id")
                finalize_from_intent(
                    order_number=order_number,
                    intent_id=str(intent_id),
                    intent_status=_ev_get(obj, "status") or "succeeded",
                    amount=amount,
                    email=_ev_get(obj, "receipt_email") or "",
                )
        elif etype == "payment_intent.payment_failed":
            meta = dict(_ev_get(obj, "metadata") or {})
            # Don't finalize; just record for ops visibility.
            import logging
            logging.getLogger("orders").warning(
                "Stripe payment_failed for order %s", meta.get("order_number"))
        elif etype == "charge.refunded":
            apply_stripe_refund(
                payment_intent_id=str(_ev_get(obj, "payment_intent") or ""),
                amount_refunded_cents=_ev_get(obj, "amount_refunded") or 0,
            )
    except Exception:
        import logging
        logging.getLogger("orders").exception("Stripe webhook handler error (%s)", etype)
        # Return 200 so Stripe doesn't hammer retries on our own bug; we logged it.

    return HttpResponse(status=200)


def _can_access_order(request, order):
    """Owner (authed), guest who placed it (session match), or staff."""
    if request.user.is_authenticated:
        if request.user.is_staff or (order.user_id and order.user_id == request.user.id):
            return True
    sk = request.session.session_key
    if order.is_guest and sk and order.session_key == sk:
        return True
    return False


def invoice_pdf(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, is_ordered=True)
    if not _can_access_order(request, order):
        return HttpResponse("Not authorized", status=403)
    items = OrderProduct.objects.filter(order=order).select_related("product").prefetch_related("variations")

    from .receipt_pdf import build_receipt_pdf
    pdf = build_receipt_pdf(order, items)

    # ?disposition=inline -> render in-browser (preview); default -> download.
    inline = (request.GET.get("disposition") or "").lower() == "inline"
    response = HttpResponse(pdf, content_type="application/pdf")
    disp = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{disp}; filename="receipt_{order.order_number}.pdf"'
    return response

    c.showPage()
    c.save()
    return response


@require_POST
def payments(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        messages.error(request, "Invalid payment confirmation payload.")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_id = body.get("orderID")
    trans_id = body.get("transID")
    status = body.get("status")
    method = body.get("payment_method")

    if not all([order_id, trans_id, status, method]):
        messages.error(request, "Payment data missing. Please try again.")
        return JsonResponse({"error": "missing_fields"}, status=400)

    order = _resolve_pending_order(request, order_id)
    if not order:
        messages.error(request, "Order not found or already confirmed.")
        return JsonResponse({"error": "order_not_found"}, status=404)

    # SECURITY: never trust the client's "status". This endpoint serves PayPal, whose
    # capture MUST be verified server-side against PayPal's API before we mark the order
    # paid (amount + currency + COMPLETED). PayPal is fail-closed: if it isn't configured/
    # enabled, no order can be finalized here. (Stripe uses its own server-verified intent
    # + signed-webhook path and never reaches this endpoint.)
    from .paypal import paypal_available, verify_capture
    if not paypal_available():
        logging.getLogger("orders").info("PayPal payment attempt while PayPal disabled (order %s)", order.order_number)
        return JsonResponse({"error": "paypal_unavailable",
                             "message": "PayPal is temporarily unavailable. Please use card."}, status=503)
    ok, reason = verify_capture(trans_id, order.order_total, getattr(order, "currency", "") or settings.PAYPAL_CURRENCY)
    if not ok:
        logging.getLogger("orders").warning("PayPal capture rejected (%s) for order %s", reason, order.order_number)
        return JsonResponse({"error": "payment_unverified", "reason": reason}, status=402)

    # Verified: idempotent Payment create (amount comes from the order, not the client).
    payment, _created = Payment.objects.get_or_create(
        payment_id=trans_id,
        defaults={
            "user": order.user,
            "email": order.email,
            "payment_method": "PayPal",
            "amount_paid": str(order.order_total),
            "status": "COMPLETED",
        }
    )

    if not order.is_ordered:
        try:
            finalize_order_payment(order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return JsonResponse({"error": "finalize_failed"}, status=500)

    messages.success(request, "Payment successful. Your order is confirmed.")
    return JsonResponse({
        "order_number": order.order_number,
        "transID": payment.payment_id,
    })


def _place_order_cart_items(request):
    """Active cart for authed user or guest session (creating a session if needed)."""
    if request.user.is_authenticated:
        return list(CartItem.objects.filter(user=request.user, is_active=True)), None
    if not request.session.session_key:
        request.session.create()
    from carts.models import Cart
    cart = Cart.objects.filter(cart_id=request.session.session_key).first()
    items = list(CartItem.objects.filter(cart=cart, is_active=True)) if cart else []
    return items, request.session.session_key


# --------------------------------------------------------------------------- #
# Checkout protection + field preservation
# --------------------------------------------------------------------------- #
CHECKOUT_RESTORE_KEY = "checkout_restore"        # session stash: typed fields + field errors
_CHECKOUT_FIELDS = ("first_name", "last_name", "email", "phone", "phone_prefix",
                    "address_line_1", "address_line_2", "city", "state",
                    "postal_code", "country", "order_note")


def _stash_checkout(request, form=None, extra_errors=None, address_warning=""):
    """Preserve what the shopper typed (and per-field errors) across the redirect —
    an invalid submit must never wipe ten fields because one was wrong."""
    data = {f: (request.POST.get(f) or "")[:200] for f in _CHECKOUT_FIELDS}
    errors = {}
    if form is not None:
        for field, errs in form.errors.items():
            errors[field] = str(errs[0]) if errs else ""
    if extra_errors:
        errors.update(extra_errors)
    request.session[CHECKOUT_RESTORE_KEY] = {"data": data, "errors": errors,
                                             "address_warning": address_warning}


def _checkout_guard(request):
    """Anti-bot: honeypot + minimum form time + a light rate limit. Returns an error
    string (safe, generic) when the submission looks automated, else None.
    Never blocks legitimate shoppers: the honeypot is invisible, the minimum time is
    3 seconds and the rate limit allows 8 attempts per 10 minutes."""
    from django.core.cache import cache
    from django.core import signing

    # 1) honeypot — real browsers never fill it
    if (request.POST.get("website") or "").strip():
        return "bot"

    # 2) minimum form time (signed server timestamp rendered into the form)
    token = request.POST.get("form_ts") or ""
    try:
        issued = signing.loads(token, salt="checkout-ts", max_age=3600)
        import time
        if time.time() - float(issued) < 3:
            return "too_fast"
    except (signing.BadSignature, ValueError, TypeError):
        return "bad_token"

    # 3) rate limit per session/IP (cache-based, no PII stored — key is hashed)
    import hashlib
    ident = request.session.session_key or (request.META.get("REMOTE_ADDR") or "?")
    key = "co_rl:" + hashlib.sha256(ident.encode()).hexdigest()[:24]
    n = cache.get(key, 0)
    if n >= 8:
        return "rate_limited"
    cache.set(key, n + 1, 600)
    return None


def place_order(request, total=0, quantity=0):
    from django.utils import translation
    from orders.totals import compute_cart_totals
    from shipping.geo import detect_country

    current_user = request.user
    is_authed = current_user.is_authenticated

    cart_items, session_key = _place_order_cart_items(request)
    if len(cart_items) <= 0:
        messages.info(request, "Your cart is empty.")
        return redirect("store")

    if request.method != "POST":
        messages.warning(request, "Please complete your billing details to continue.")
        return redirect("checkout")

    bot = _checkout_guard(request)
    if bot:
        # Generic message — no detail an automation author could use.
        messages.error(request, _("We could not process this request. Please try again."))
        return redirect("checkout")

    form = OrderForm(request.POST)
    if not form.is_valid():
        _stash_checkout(request, form)
        messages.error(request, _("Please review the highlighted fields and try again."))
        return redirect("checkout")

    # Address country has priority over IP for the final quote.
    country = (form.cleaned_data["country"] or detect_country(request)).upper()
    totals = compute_cart_totals(cart_items, country)
    quote = totals.shipping_quote

    if not quote.available:
        _stash_checkout(request, extra_errors={"country": str(_("We don't ship to this country yet."))})
        messages.error(request, _("We're sorry, we don't ship to the selected country yet."))
        return redirect("checkout")

    # ---- Address verification contract (professional Google address flow) -------------
    # Modes: disabled (local checks + confirm flow) / warning (unverified needs the explicit
    # "I confirm" checkbox) / strict (a Places selection is REQUIRED and, with a server key,
    # re-verified fail-closed — hidden fields alone are never trusted).
    from shipping.address_validation import effective_mode, validate_address, verify_for_order
    from shipping.models import CheckoutApiConfig
    _api_cfg = CheckoutApiConfig.load()
    _mode = effective_mode(_api_cfg)
    _place_id = (request.POST.get("google_place_id") or "").strip()[:128]
    _manual_confirmed = bool(request.POST.get("address_confirmed"))
    _addr_verified = False

    if _mode == "strict":
        ok, err = verify_for_order(_api_cfg, form.cleaned_data, _place_id)
        if not ok:
            _stash_checkout(request, address_warning=str(err))
            messages.error(request, _("Please select a verified address from the suggestions."))
            return redirect("checkout")
        _addr_verified = True
    else:
        # warning/disabled: honest local (+optional Google, fail-open) check; unverified
        # addresses can proceed only through the explicit confirmation checkbox.
        _addr_verified = bool(_place_id) and request.POST.get("address_verified") == "true"
        if not _manual_confirmed and not _addr_verified:
            level, warn_msg = validate_address(form.cleaned_data, _api_cfg)
            if level == "warning" or (_mode == "warning" and not _addr_verified):
                msg = str(warn_msg) if level == "warning" else str(
                    _("This address is not verified. Confirm it to continue, or pick it from "
                      "the suggestions."))
                _stash_checkout(request, address_warning=msg)
                messages.warning(request, _("Please review your address below."))
                return redirect("checkout")

    data = Order()
    data.google_place_id = _place_id
    data.address_verified = _addr_verified
    data.address_manual_confirmed = _manual_confirmed and not _addr_verified
    if is_authed:
        data.user = current_user
    else:
        data.user = None
        data.is_guest = True
        data.session_key = session_key or ""
    data.first_name = form.cleaned_data["first_name"]
    data.last_name = form.cleaned_data["last_name"]
    data.phone = form.cleaned_data["phone"]
    data.email = form.cleaned_data["email"]
    data.address_line_1 = form.cleaned_data["address_line_1"]
    data.address_line_2 = form.cleaned_data["address_line_2"]
    data.country = country
    data.state = form.cleaned_data["state"]
    data.postal_code = form.cleaned_data["postal_code"]
    data.city = form.cleaned_data["city"]
    data.order_note = form.cleaned_data["order_note"]
    data.currency = totals.currency
    data.items_subtotal = totals.items_subtotal
    data.shipping_cost = totals.shipping_cost
    data.tax = totals.tax
    data.order_total = totals.grand_total
    data.shipping_country = country[:2]
    data.shipping_min_days = quote.min_days
    data.shipping_max_days = quote.max_days
    data.language_code = (translation.get_language() or "en")[:5]
    data.ip = request.META.get("REMOTE_ADDR")
    data.save()

    # Generate order number: YYYYMMDD + id
    current_date = datetime.date.today().strftime("%Y%m%d")
    data.order_number = current_date + str(data.id)
    data.save(update_fields=["order_number"])

    # Stash a validated session coupon on the pending order (re-validated, anti-abuse
    # enforced). The redemption is recorded only once the order is PAID (finalize), so an
    # abandoned checkout never consumes a usage / burns a one-time coupon.
    try:
        from promotions.services import quote_for_order
        code, discount = quote_for_order(request, totals.items_subtotal)
        if discount and discount > 0:
            data.discount = float(discount)
            data.coupon_code = (code or "")[:32]
            data.order_total = max(0.0, float(totals.grand_total) - float(discount))
            data.save(update_fields=["discount", "coupon_code", "order_total"])
    except Exception:
        pass

    # Save/update default address (authed only)
    if request.POST.get("save_address") and is_authed:
        payload = dict(
            first_name=data.first_name, last_name=data.last_name, email=data.email,
            phone=data.phone, address_line_1=data.address_line_1,
            address_line_2=data.address_line_2, city=data.city, state=data.state,
            country=data.country, postal_code=data.postal_code,
        )
        default_addr = Address.objects.filter(user=current_user, is_default=True).first()
        if default_addr:
            for k, v in payload.items():
                setattr(default_addr, k, v)
            default_addr.save()
        else:
            Address.objects.filter(user=current_user, is_default=True).update(is_default=False)
            Address.objects.create(user=current_user, is_default=True, **payload)

    context = {
        "order": data,
        "cart_items": cart_items,
        "total": totals.items_subtotal,
        "tax": totals.tax,
        "shipping_cost": totals.shipping_cost,
        "discount": data.discount,
        "coupon_code": data.coupon_code,
        "grand_total": data.order_total,
    }
    from payments import config as _pconf
    context["stripe_ready"] = bool(_pconf.stripe_secret_key() and _pconf.stripe_publishable_key())
    return render(request, "orders/payments.html", context)


def order_complete(request):
    order_number = request.GET.get("order_number")
    transID = request.GET.get("payment_id")

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)

        purchased_ids = [op.product_id for op in ordered_products]
        cats = [op.product.category_id for op in ordered_products if op.product_id]

        recommended_products = (
            Product.objects.filter(is_available=True, category_id__in=cats)
            .exclude(id__in=purchased_ids)
            .order_by("?")[:8]
        )

        subtotal = 0
        for i in ordered_products:
            subtotal += i.product_price * i.quantity

        payment = Payment.objects.get(payment_id=transID)

        context = {
            "order": order,
            "ordered_products": ordered_products,
            "order_number": order.order_number,
            "transID": payment.payment_id,
            "payment": payment,
            "subtotal": subtotal,
            "recommended_products": recommended_products,
        }
        return render(request, "orders/order_complete.html", context)

    except (Payment.DoesNotExist, Order.DoesNotExist):
        messages.error(request, "We couldn't find your order confirmation. Please contact support.")
        return redirect("home")
