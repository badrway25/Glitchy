from django.db import transaction
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.http import JsonResponse
from carts.models import CartItem
from django.conf import settings
from store.models import Product
from .models import OrderProduct
from .printify import create_order, send_to_production
from .printify_payload import build_printify_payload  

def push_order_to_printify(order, *, auto_send=True):
    # idempotenza
    if order.printify_order_id:
        return order.printify_order_id

    ops = (
        OrderProduct.objects
        .select_related("product")
        .prefetch_related("variations")
        .filter(order=order)
    )

    try:
        payload = build_printify_payload(order=order, order_products=ops)  # ✅ usa quello giusto
        res = create_order(payload)

        order.printify_order_id = res.get("id")
        order.printify_status = res.get("status") or "created"
        order.printify_last_error = ""
        order.save(update_fields=["printify_order_id", "printify_status", "printify_last_error"])

        if auto_send and order.printify_order_id:
            send_to_production(order.printify_order_id)
            order.printify_status = "sent_to_production"
            order.save(update_fields=["printify_status"])

        return order.printify_order_id

    except Exception as e:
        # salva sempre l’errore
        order.printify_status = "error"
        order.printify_last_error = str(e)
        order.save(update_fields=["printify_status", "printify_last_error"])
        raise

def build_printify_payload(*, order, order_products):
    address_to = {
        "first_name": order.first_name,
        "last_name": order.last_name,
        "email": order.email,
        "phone": order.phone,
        "country": order.country,        # meglio ISO2, es: "IT"
        "region": order.state or "",
        "address1": order.address_line_1,
        "address2": order.address_line_2 or "",
        "city": order.city,
        "zip": getattr(order, "postal_code", "") or "",  # se non hai zip, aggiungilo
    }

    line_items = []
    for op in order_products:
        p = op.product

        if not getattr(p, "printify_product_id", None):
            raise ValueError(f"Missing printify_product_id for product {p.id}")

        # Qui devi avere una mappa variant_id Printify
        variant_id = None
        for v in op.variations.all():
            if getattr(v, "printify_variant_id", None):
                variant_id = v.printify_variant_id
                break

        if not variant_id:
            raise ValueError(f"Missing printify_variant_id for order item {op.id}")

        line_items.append({
            "product_id": p.printify_product_id,
            "variant_id": variant_id,
            "quantity": op.quantity,
        })

    return {
        "external_id": str(order.order_number),
        "label": f"Order {order.order_number}",
        "line_items": line_items,
        "send_shipping_notification": True,
        "address_to": address_to,
    }


@transaction.atomic
def finalize_order_payment(*, request, order, payment):
    """
    - collega payment a order
    - sposta cart_items -> OrderProduct
    - decrementa stock
    - svuota carrello
    - invia email (fail_silently in dev)
    """
    # attach payment + close order
    order.payment = payment
    order.is_ordered = True
    order.status = "Accepted"
    order.save(update_fields=["payment", "is_ordered", "status"])

    cart_items = CartItem.objects.select_related("product").prefetch_related("variations").filter(
        user=request.user, is_active=True
    )

    for item in cart_items:
        op = OrderProduct.objects.create(
            order_id=order.id,
            payment=payment,
            user_id=request.user.id,
            product_id=item.product_id,
            quantity=item.quantity,
            product_price=item.product.price,
            ordered=True,
        )
        op.variations.set(item.variations.all())

        # reduce stock
        product = item.product
        product.stock = max(0, product.stock - item.quantity)
        # se stock va a 0, puoi anche settare is_available=False
        if product.stock <= 0:
            product.is_available = False
        product.save()

    # clear cart
    CartItem.objects.filter(user=request.user).delete()

    # ✅ AUTO SEND TO PRINTIFY
    try:
        push_order_to_printify(order, auto_send=False)  # test mode
    except Exception as e:
        order.printify_status = "error"
        order.printify_last_error = str(e)
        order.save(update_fields=["printify_status", "printify_last_error"])

    # email (non far crashare dev)
    try:
        mail_subject = f"Order confirmed • #{order.order_number}"
        message = render_to_string("orders/order_recieved_email.html", {
            "user": request.user,
            "order": order,
            "site_name": "Glitchy",  # opzionale
        })
        to_email = request.user.email

        email = EmailMessage(mail_subject, message, to=[to_email])
        email.content_subtype = "html"  # ✅ IMPORTANTISSIMO: invia come HTML
        email.send(fail_silently=True)
    except Exception:
        pass
