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


@login_required(login_url="login")
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
    try:
        order = Order.objects.get(user=request.user, order_number=order_number, is_ordered=False)
    except Order.DoesNotExist:
        messages.error(request, "Order not found or already confirmed.")
        return redirect("checkout")

    if intent.status != "succeeded":
        messages.error(request, f"Payment not completed (status: {intent.status}).")
        return redirect("payments")

    # idempotent-ish Payment create
    payment, _created = Payment.objects.get_or_create(
        user=request.user,
        payment_id=intent.id,
        defaults={
            "payment_method": "Stripe",
            "amount_paid": str(order.order_total),
            "status": intent.status,
        }
    )

    # finalize only if not already ordered
    if not order.is_ordered:
        try:
            finalize_order_payment(request=request, order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return redirect("home")

    messages.success(request, "Payment successful. Your order is confirmed.")
    return redirect(f"{reverse('order_complete')}?order_number={order.order_number}&payment_id={payment.payment_id}")


@login_required(login_url="login")
@require_POST
def stripe_create_intent(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_number = data.get("order_number")
    if not order_number:
        return JsonResponse({"error": "Missing order_number"}, status=400)

    try:
        order = Order.objects.get(user=request.user, order_number=order_number, is_ordered=False)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    try:
        amount_cents = int(round(float(order.order_total) * 100))
    except Exception:
        return JsonResponse({"error": "Invalid order total"}, status=400)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            metadata={"order_number": order.order_number, "user_id": str(request.user.id)},
            automatic_payment_methods={"enabled": True},
        )
    except Exception:
        return JsonResponse({"error": "Stripe intent creation failed"}, status=500)

    return JsonResponse({
        "clientSecret": intent.client_secret,
        "publishableKey": settings.STRIPE_PUBLIC_KEY,
    })


@login_required(login_url="login")
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

    try:
        order = Order.objects.get(user=request.user, order_number=order_number, is_ordered=False)
    except Order.DoesNotExist:
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

    # idempotent-ish Payment create
    payment, _created = Payment.objects.get_or_create(
        user=request.user,
        payment_id=intent.id,
        defaults={
            "payment_method": "Stripe",
            "amount_paid": str(order.order_total),
            "status": intent.status,
        }
    )

    # finalize only if needed
    if not order.is_ordered:
        try:
            finalize_order_payment(request=request, order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return JsonResponse({"error": "finalize_failed"}, status=500)

    messages.success(request, "Payment successful. Your order is confirmed.")
    return JsonResponse({
        "order_number": order.order_number,
        "transID": payment.payment_id,
    })


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        _order_number = intent.get("metadata", {}).get("order_number")
        # opzionale: finalizzare server-side in modo idempotente

    return HttpResponse(status=200)


def invoice_pdf(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, is_ordered=True)
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

    subtotal = float(order.order_total) - float(order.tax)
    c.setFont("Helvetica", 10)
    c.drawRightString(width - x, y, f"Subtotal: € {subtotal:.2f}")
    y -= 6 * mm
    c.drawRightString(width - x, y, f"Tax: € {float(order.tax):.2f}")
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - x, y, f"Grand Total: € {float(order.order_total):.2f}")

    c.showPage()
    c.save()
    return response


@login_required(login_url="login")
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

    try:
        order = Order.objects.get(user=request.user, is_ordered=False, order_number=order_id)
    except Order.DoesNotExist:
        messages.error(request, "Order not found or already confirmed.")
        return JsonResponse({"error": "order_not_found"}, status=404)

    # idempotent-ish Payment create
    payment, _created = Payment.objects.get_or_create(
        user=request.user,
        payment_id=trans_id,
        defaults={
            "payment_method": method,
            "amount_paid": str(order.order_total),
            "status": status,
        }
    )

    if not order.is_ordered:
        try:
            finalize_order_payment(request=request, order=order, payment=payment)
        except Exception:
            messages.error(request, "Payment succeeded, but we couldn't finalize your order. Please contact support.")
            return JsonResponse({"error": "finalize_failed"}, status=500)

    messages.success(request, "Payment successful. Your order is confirmed.")
    return JsonResponse({
        "order_number": order.order_number,
        "transID": payment.payment_id,
    })


def place_order(request, total=0, quantity=0):
    current_user = request.user

    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    if cart_count <= 0:
        messages.info(request, "Your cart is empty.")
        return redirect("store")

    grand_total = 0
    tax = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (2 * total) / 100
    grand_total = total + tax

    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data["first_name"]
            data.last_name = form.cleaned_data["last_name"]
            data.phone = form.cleaned_data["phone"]
            data.email = form.cleaned_data["email"]
            data.address_line_1 = form.cleaned_data["address_line_1"]
            data.address_line_2 = form.cleaned_data["address_line_2"]
            data.country = form.cleaned_data["country"]
            data.state = form.cleaned_data["state"]
            data.postal_code = form.cleaned_data["postal_code"]
            data.city = form.cleaned_data["city"]
            data.order_note = form.cleaned_data["order_note"]
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get("REMOTE_ADDR")
            data.save()

            # Generate order number
            yr = int(datetime.date.today().strftime("%Y"))
            dt = int(datetime.date.today().strftime("%d"))
            mt = int(datetime.date.today().strftime("%m"))
            d = datetime.date(yr, mt, dt)
            current_date = d.strftime("%Y%m%d")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            # Save/Update default address
            save_address = request.POST.get("save_address")  # "on" if checked
            if save_address and request.user.is_authenticated:
                payload = dict(
                    first_name=data.first_name,
                    last_name=data.last_name,
                    email=data.email,
                    phone=data.phone,
                    address_line_1=data.address_line_1,
                    address_line_2=data.address_line_2,
                    city=data.city,
                    state=data.state,
                    country=data.country,
                    postal_code=data.postal_code, 
                )

                default_addr = Address.objects.filter(user=current_user, is_default=True).first()
                if default_addr:
                    for k, v in payload.items():
                        setattr(default_addr, k, v)
                    default_addr.save()
                else:
                    Address.objects.filter(user=current_user, is_default=True).update(is_default=False)
                    Address.objects.create(user=current_user, is_default=True, **payload)

            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)
            context = {
                "order": order,
                "cart_items": cart_items,
                "total": total,
                "tax": tax,
                "grand_total": grand_total,
            }
            return render(request, "orders/payments.html", context)

        # ❗ form not valid
        messages.error(request, "Please check your billing details and try again.")
        return redirect("checkout")

    messages.warning(request, "Please complete your billing details to continue.")
    return redirect("checkout")


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
