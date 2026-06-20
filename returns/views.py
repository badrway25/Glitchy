from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from orders.models import Order, OrderProduct
from .forms import ReturnRequestForm
from .models import ReturnItem, ReturnRequest
from .services import default_refund_amount, eligibility_for_order, return_window_days


def returns_policy(request):
    """Public returns & refunds policy page."""
    return render(request, "returns/policy.html", {"window_days": return_window_days()})


def _authorize(request, order):
    """Return (authorized, require_email). Authed owner is auto-authorized."""
    if request.user.is_authenticated and order.user_id and order.user_id == request.user.id:
        return True, False
    return False, True  # guest must prove the order email


def request_return(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, is_ordered=True)
    items = OrderProduct.objects.filter(order=order).select_related("product").prefetch_related("variations")
    eligibility = eligibility_for_order(order)
    auto_ok, require_email = _authorize(request, order)

    # Already has an open return?
    existing = order.returns.filter(status__in=ReturnRequest.OPEN_STATUSES).first()

    if request.method == "POST":
        form = ReturnRequestForm(request.POST, require_email=require_email)

        if not eligibility.eligible:
            messages.error(request, _("This order is outside the %(d)d-day return window.") % {"d": return_window_days()})
            return redirect("returns:request", order_number=order_number)

        if existing:
            messages.info(request, _("There is already an open return for this order."))
            return redirect("returns:status", token=existing.public_token)

        if form.is_valid():
            # Verify guest email matches the order.
            if require_email and not auto_ok:
                if form.cleaned_data["email"].strip().lower() != (order.email or "").strip().lower():
                    messages.error(request, _("That email does not match this order."))
                    return redirect("returns:request", order_number=order_number)

            rr = ReturnRequest.objects.create(
                order=order,
                customer_email=order.email,
                reason=form.cleaned_data.get("reason", ""),
                within_window=True,
                refund_amount=default_refund_amount(order),
            )
            # Selected items (default: all items, all quantities).
            selected_ids = request.POST.getlist("item")
            for op in items:
                if selected_ids and str(op.id) not in selected_ids:
                    continue
                try:
                    qty = int(request.POST.get(f"qty_{op.id}", op.quantity))
                except (TypeError, ValueError):
                    qty = op.quantity
                qty = max(1, min(qty, op.quantity))
                ReturnItem.objects.create(return_request=rr, order_product=op, quantity=qty)

            # Notify customer + internal team via n8n (SMTP fallback).
            try:
                from notifications.notify import notify_return_event
                from notifications import events as ev

                notify_return_event(rr, ev.RETURN_REQUESTED)
            except Exception:
                pass

            messages.success(request, _("Your return request has been submitted. We'll be in touch shortly."))
            return redirect("returns:status", token=rr.public_token)
    else:
        form = ReturnRequestForm(require_email=require_email)

    context = {
        "order": order,
        "items": items,
        "form": form,
        "eligibility": eligibility,
        "window_days": return_window_days(),
        "existing": existing,
        "require_email": require_email,
    }
    return render(request, "returns/request.html", context)


def return_status(request, token):
    rr = get_object_or_404(ReturnRequest.objects.select_related("order"), public_token=token)
    return render(request, "returns/status.html", {
        "rr": rr,
        "order": rr.order,
        "items": rr.items.select_related("order_product__product").all(),
    })
