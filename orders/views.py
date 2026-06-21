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

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


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

    try:
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
    except Exception:
        return JsonResponse({"error": "Stripe intent creation failed"}, status=500)

    return JsonResponse({
        "clientSecret": intent.client_secret,
        "publishableKey": settings.STRIPE_PUBLIC_KEY,
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
    secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        # Invalid signature / payload — reject (no secret logged).
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
    items = OrderProduct.objects.filter(order=order)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{order.order_number}.pdf"'

    c = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    x = 18 * mm
    y = height - 20 * mm

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Invoice")
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Order: #{order.order_number}")
    y -= 5 * mm
    c.drawString(x, y, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
    y -= 10 * mm

    # Customer
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Invoiced to")
    y -= 6 * mm

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"{order.first_name} {order.last_name}")
    y -= 5 * mm
    address2 = f" {order.address_line_2}" if order.address_line_2 else ""
    c.drawString(x, y, f"{order.address_line_1}{address2}".strip())
    y -= 5 * mm
    c.drawString(x, y, f"{order.city}, {order.state},{order.postal_code},  {order.country}")
    y -= 5 * mm
    c.drawString(x, y, f"{order.email} • {order.phone}")
    y -= 12 * mm

    # Table header
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Product")
    c.drawString(x + 120 * mm, y, "Qty")
    c.drawRightString(width - x, y, "Total")
    y -= 6 * mm
    c.line(x, y, width - x, y)
    y -= 8 * mm

    # Items
    c.setFont("Helvetica", 10)
    for it in items:
        if y < 30 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("Helvetica", 10)

        line_total = float(it.product_price) * int(it.quantity)
        c.drawString(x, y, it.product.product_name[:45])
        c.drawString(x + 120 * mm, y, str(it.quantity))
        c.drawRightString(width - x, y, f"€ {line_total:.2f}")
        y -= 5 * mm

        vars_qs = it.variations.all()
        if vars_qs.exists():
            vars_str = ", ".join([f"{v.variation_category}: {v.variation_value}" for v in vars_qs])[:80]
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(x, y, vars_str)
            c.setFont("Helvetica", 10)
            y -= 6 * mm
        else:
            y -= 2 * mm

    y -= 2 * mm
    c.line(x, y, width - x, y)
    y -= 10 * mm

    subtotal = float(order.items_subtotal) or (float(order.order_total) - float(order.tax) - float(order.shipping_cost))
    c.setFont("Helvetica", 10)
    c.drawRightString(width - x, y, f"Subtotal: € {subtotal:.2f}")
    y -= 6 * mm
    c.drawRightString(width - x, y, f"Shipping: € {float(order.shipping_cost):.2f}")
    y -= 6 * mm
    c.drawRightString(width - x, y, f"Tax: € {float(order.tax):.2f}")
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - x, y, f"Grand Total: € {float(order.order_total):.2f}")

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

    # idempotent-ish Payment create
    payment, _created = Payment.objects.get_or_create(
        payment_id=trans_id,
        defaults={
            "user": order.user,
            "email": order.email,
            "payment_method": method,
            "amount_paid": str(order.order_total),
            "status": status,
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

    form = OrderForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check your billing details and try again.")
        return redirect("checkout")

    # Address country has priority over IP for the final quote.
    country = (form.cleaned_data["country"] or detect_country(request)).upper()
    totals = compute_cart_totals(cart_items, country)
    quote = totals.shipping_quote

    if not quote.available:
        messages.error(request, "We're sorry, we don't ship to the selected country yet.")
        return redirect("checkout")

    data = Order()
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

    # Apply a session coupon (re-validated at checkout, anti-abuse enforced).
    try:
        from promotions.services import record_redemption, SESSION_KEY
        code = request.session.get(SESSION_KEY)
        discount = record_redemption(request, data, totals.items_subtotal)
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
