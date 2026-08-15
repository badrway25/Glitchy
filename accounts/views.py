from .forms import RegistrationForm
from .models import Account
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from django.http import HttpResponse

# Verification email
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.shortcuts import render, redirect, get_object_or_404
from carts.views import _cart_id
from carts.models import Cart, CartItem
import requests

from .models import Address
from .forms import AddressForm

from django.core.paginator import Paginator

from orders.models import Order, OrderProduct  # <-- aggiungi

from django.db.models import Sum, Q
from django.urls import reverse
from django.utils import timezone

@login_required(login_url='login')
def transactions(request):
    user = request.user

    # Mostriamo solo ordini effettivamente piazzati (is_ordered=True) e con pagamento collegato
    qs = (
        Order.objects
        .filter(user=user, is_ordered=True, payment__isnull=False)
        .select_related('payment')
        .order_by('-created_at')
    )

    # --- filtri ---
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    method = (request.GET.get("method") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if method:
        qs = qs.filter(payment__payment_method__iexact=method)

    if q:
        qs = qs.filter(
            Q(order_number__icontains=q) |
            Q(payment__payment_id__icontains=q)
        )

    # --- paginazione ---
    paginator = Paginator(qs, 10)
    page = request.GET.get("page")
    transactions_page = paginator.get_page(page)

    context = {
        "transactions": transactions_page,
        "q": q,
        "status": status,
        "method": method,
        "status_options": ["New", "Accepted", "Completed", "Cancelled"],
        # Metti qui i metodi che usi davvero (PayPal sicuro, Payconiq se lo aggiungerai)
        "method_options": ["PayPal", "Payconiq"],
    }
    return render(request, "accounts/transactions.html", context)


def _wishlist_count(user):
    try:
        from wishlist.models import WishlistItem
        return WishlistItem.objects.filter(user=user).count()
    except Exception:
        return 0


@login_required(login_url='login')
def dashboard(request):
    user = request.user

    orders_qs = Order.objects.filter(user=user, is_ordered=True).order_by('-created_at')

    total_orders = orders_qs.count()
    total_spent = orders_qs.aggregate(total=Sum("order_total"))["total"] or 0
    pending_count = orders_qs.filter(status__in=["New", "Accepted"]).count()
    completed_count = orders_qs.filter(status="Completed").count()
    cancelled_count = orders_qs.filter(status="Cancelled").count()
    receipts_available = orders_qs.filter(payment__isnull=False).count()

    addresses_count = Address.objects.filter(user=user).count()
    has_default_address = Address.objects.filter(user=user, is_default=True).exists()
    wishlist_count = _wishlist_count(user)

    # 5 most recent — payment fetched in one query (no N+1 in the table).
    recent_orders = list(orders_qs.select_related("payment")[:5])

    # "Recent activity" — derived from REAL data only (no fake events).
    activity = []
    for o in recent_orders:
        activity.append({"icon": "shopping-bag", "title": _("Order placed"),
                         "ref": "#" + o.order_number, "when": o.created_at,
                         "url": reverse("order_detail", args=[o.order_number])})
        if o.payment_id:
            activity.append({"icon": "file", "title": _("Receipt available"),
                             "ref": "#" + o.order_number, "when": o.created_at,
                             "url": reverse("billing")})
    last_addr = Address.objects.filter(user=user).order_by("-updated_at").first()
    if last_addr:
        activity.append({"icon": "map-marker", "title": _("Delivery address updated"),
                         "ref": last_addr.city, "when": last_addr.updated_at,
                         "url": reverse("address_list")})
    # Wishlist saves — real WishlistItem.created_at timestamps (no invented events).
    try:
        from wishlist.models import WishlistItem
        for wi in (WishlistItem.objects.filter(user=user).select_related("product")
                   .order_by("-created_at")[:3]):
            pname = getattr(wi.product, "product_name", "") if wi.product_id else ""
            activity.append({"icon": "heart", "title": _("Saved to wishlist"),
                             "ref": (pname or "")[:32], "when": wi.created_at,
                             "url": reverse("wishlist:saved")})
    except Exception:
        pass
    activity.sort(key=lambda a: a["when"] or timezone.now(), reverse=True)
    activity = activity[:7]

    # Smart, actionable alerts (only when genuinely useful).
    alerts = []
    if receipts_available:
        alerts.append({"tone": "info", "icon": "file", "count": receipts_available,
                       "text": _("receipt(s) ready to download"),
                       "url": reverse("billing"), "cta": _("Open billing")})
    if addresses_count == 0:
        alerts.append({"tone": "warn", "icon": "map-marker", "count": 0,
                       "text": _("Add a delivery address to speed up checkout."),
                       "url": reverse("address_create"), "cta": _("Add address")})
    if wishlist_count:
        alerts.append({"tone": "soft", "icon": "heart", "count": wishlist_count,
                       "text": _("item(s) saved for later"),
                       "url": reverse("wishlist:saved"), "cta": _("View saved")})

    context = {
        "orders": recent_orders,
        "total_orders": total_orders,
        "total_spent": total_spent,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
        "receipts_available": receipts_available,
        "addresses_count": addresses_count,
        "has_default_address": has_default_address,
        "wishlist_count": wishlist_count,
        "activity": activity,
        "alerts": alerts,
    }
    return render(request, "accounts/dashboard.html", context)


# Customer-facing order statuses (the model's STATUS choices).
ORDER_STATUS_OPTIONS = ["New", "Accepted", "Completed", "Cancelled"]

# Order list sort options -> (label key, ORM ordering). Whitelisted so the
# `sort` query param can never inject an arbitrary field.
ORDER_SORT_OPTIONS = {
    "recent": ("Newest first", "-created_at"),
    "oldest": ("Oldest first", "created_at"),
    "high": ("Highest total", "-order_total"),
    "low": ("Lowest total", "order_total"),
}


def _parse_date(s):
    from datetime import datetime
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_amount(s):
    import math
    try:
        v = float(str(s).strip())
        return v if math.isfinite(v) and v >= 0 else None
    except (ValueError, TypeError):
        return None


def _filter_sort_orders(request, base_qs):
    """Shared search + status + date range + total range + receipt + sort for the
    orders / billing lists. Every input is validated/whitelisted (no field injection).
    Search matches the order number or any purchased product name."""
    q = (request.GET.get("q") or "").strip()[:60]
    status = (request.GET.get("status") or "").strip()
    sort = (request.GET.get("sort") or "recent").strip()
    df, dt = _parse_date(request.GET.get("date_from")), _parse_date(request.GET.get("date_to"))
    tmin, tmax = _parse_amount(request.GET.get("total_min")), _parse_amount(request.GET.get("total_max"))
    receipt = (request.GET.get("receipt") or "").strip() == "1"

    qs = base_qs
    if status in ORDER_STATUS_OPTIONS:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(order_number__icontains=q) |
            Q(orderproduct__product__product_name__icontains=q)
        ).distinct()
    if df:
        qs = qs.filter(created_at__date__gte=df)
    if dt:
        qs = qs.filter(created_at__date__lte=dt)
    if tmin is not None:
        qs = qs.filter(order_total__gte=tmin)
    if tmax is not None:
        qs = qs.filter(order_total__lte=tmax)
    if receipt:
        qs = qs.filter(payment__isnull=False)
    ordering = ORDER_SORT_OPTIONS.get(sort, ORDER_SORT_OPTIONS["recent"])[1]
    qs = qs.order_by(ordering)

    active = {
        "q": q,
        "status": status if status in ORDER_STATUS_OPTIONS else "",
        "sort": sort if sort in ORDER_SORT_OPTIONS else "recent",
        "date_from": df.isoformat() if df else "",
        "date_to": dt.isoformat() if dt else "",
        "total_min": (request.GET.get("total_min") or "").strip() if tmin is not None else "",
        "total_max": (request.GET.get("total_max") or "").strip() if tmax is not None else "",
        "receipt": "1" if receipt else "",
    }
    return qs, active


@login_required(login_url='login')
def my_orders(request):
    user = request.user
    base = Order.objects.filter(user=user, is_ordered=True).select_related("payment")
    orders_qs, active = _filter_sort_orders(request, base)

    paginator = Paginator(orders_qs, 10)
    orders = paginator.get_page(request.GET.get("page"))

    # Preserve filters across pagination links.
    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "orders": orders,
        "status_options": ORDER_STATUS_OPTIONS,
        "sort_options": {k: v[0] for k, v in ORDER_SORT_OPTIONS.items()},
        "has_filters": _has_active_filters(active),
        "result_count": paginator.count,
        "querystring": params.urlencode(),
        **active,
    }
    return render(request, "accounts/my_orders.html", context)


def _has_active_filters(active):
    return bool(active["q"] or active["status"] or active["date_from"] or active["date_to"]
                or active["total_min"] or active["total_max"] or active["receipt"]
                or active["sort"] != "recent")


@login_required(login_url="login")
def billing(request):
    """Billing / receipts center — every placed order has a downloadable receipt
    (PDF). Honest wording: these are order receipts, not fiscal invoices."""
    user = request.user
    base = Order.objects.filter(user=user, is_ordered=True).select_related("payment")
    orders_qs, active = _filter_sort_orders(request, base)

    paginator = Paginator(orders_qs, 10)
    receipts = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    # Honest billing summary over ALL the user's orders (not just this page).
    paid_qs = base.filter(payment__isnull=False)
    paid_count = paid_qs.count()
    summary = {
        "paid_count": paid_count,
        "paid_total": paid_qs.aggregate(t=Sum("order_total"))["t"] or 0,
        "receipts_available": paid_count,   # a receipt exists for every paid order
        "pending_count": base.filter(payment__isnull=True).count(),
    }

    context = {
        "receipts": receipts,
        "status_options": ORDER_STATUS_OPTIONS,
        "sort_options": {k: v[0] for k, v in ORDER_SORT_OPTIONS.items()},
        "has_filters": _has_active_filters(active),
        "result_count": paginator.count,
        "summary": summary,
        "querystring": params.urlencode(),
        **active,
    }
    return render(request, "accounts/billing.html", context)


@login_required(login_url='login')
def order_detail(request, order_number):
    user = request.user
    order = get_object_or_404(Order, user=user, order_number=order_number, is_ordered=True)
    items = OrderProduct.objects.filter(order=order).select_related("product").prefetch_related("variations")

    subtotal = 0
    for it in items:
        subtotal += float(it.product_price) * int(it.quantity)

    context = {
        "order": order,
        "items": items,
        "subtotal": subtotal,
    }
    return render(request, "accounts/order_detail.html", context)


@login_required(login_url="login")
@require_POST
def order_reorder(request, order_number):
    """Buy again — re-add a past order's items (with their original variations) to the
    cart. SAFE: only touches the cart, never creates an order or takes payment; scoped to
    request.user; uses the variations already chosen on the order so nothing is re-prompted.
    Unavailable products are skipped, not faked."""
    order = get_object_or_404(Order, user=request.user, order_number=order_number, is_ordered=True)
    items = (OrderProduct.objects.filter(order=order)
             .select_related("product").prefetch_related("variations"))

    # Index the user's existing cart once (avoids an N+1 over CartItem in the loop).
    from collections import defaultdict
    cart_index = defaultdict(list)
    for ci in CartItem.objects.filter(user=request.user).prefetch_related("variations"):
        key = (ci.product_id, frozenset(ci.variations.values_list("id", flat=True)))
        cart_index[key].append(ci)

    added = skipped = 0
    for op in items:
        product = op.product
        if not product or not getattr(product, "is_available", False):
            skipped += 1
            continue
        variations = list(op.variations.all())
        key = (product.pk, frozenset(v.pk for v in variations))
        match = cart_index[key][0] if cart_index.get(key) else None
        if match:
            match.quantity += op.quantity
            match.save(update_fields=["quantity"])
        else:
            ci = CartItem.objects.create(product=product, user=request.user, quantity=op.quantity)
            if variations:
                ci.variations.add(*variations)
            # carry the purchased colour's image snapshot back into the cart
            # (validated: only if it still belongs to this product)
            if op.selected_image_id and op.selected_image.product_id == product.pk:
                ci.selected_image = op.selected_image
                ci.save(update_fields=["selected_image"])
        added += 1
    if added:
        messages.success(request, _("Added to your cart — review and check out when you're ready."))
    if skipped and not added:
        messages.info(request, _("Those items are no longer available."))
    elif skipped:
        messages.info(request, _("Some items are no longer available and were skipped."))
    return redirect("cart")


@login_required(login_url="login")
def order_help(request, order_number):
    """'Need help with this order?' — owner-only support handoff. Never exposes
    other users' orders (the queryset is scoped to request.user)."""
    order = get_object_or_404(Order, user=request.user, order_number=order_number, is_ordered=True)
    if request.method != "POST":
        return redirect("order_detail", order_number=order_number)

    topic = (request.POST.get("topic") or "general")[:40]
    note = (request.POST.get("note") or "").strip()[:1500]
    body = (f"Order help request for order #{order.order_number} (topic: {topic}).\n\n"
            f"{note or 'No additional details provided.'}")

    # analytics (no sensitive data — just the order number + topic)
    try:
        from storefront.models import AnalyticsEvent
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(name="support_order_help", path=request.path[:255],
                                      session_key=request.session.session_key or "",
                                      meta={"order": order.order_number, "topic": topic})
    except Exception:
        pass

    try:
        from notifications.models import SupportMessage
        sm = SupportMessage.objects.create(
            from_email=request.user.email, subject=f"Order help — #{order.order_number}",
            body_text=body, account=request.user)
        try:
            from notifications.dispatcher import dispatch_event
            from django.conf import settings as _s
            dispatch_event("support.order_help",
                           {"order_number": order.order_number, "topic": topic,
                            "from_email": request.user.email, "source": "order_help"},
                           recipient_email=getattr(_s, "SUPPORT_EMAIL", "") or request.user.email)
        except Exception:
            pass
    except Exception:
        pass

    messages.success(request, "Thanks — our team has your request and will email you shortly.")
    return redirect("order_detail", order_number=order_number)

@login_required(login_url="login")
def address_list(request):
    q = (request.GET.get("q") or "").strip()[:60]
    addresses = Address.objects.filter(user=request.user)
    if q:
        addresses = addresses.filter(
            Q(city__icontains=q) | Q(country__icontains=q) | Q(postal_code__icontains=q) |
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    addresses = addresses.order_by("-is_default", "-updated_at")
    return render(request, "accounts/address_list.html", {
        "addresses": addresses, "q": q, "has_query": bool(q),
        "result_count": addresses.count(),
    })

@login_required(login_url="login")
def _address_form_extras(request, form=None):
    """Checkout-parity context for the address form: flag dial prefixes + Google config."""
    from shipping.constants import COUNTRIES
    from shipping.models import CheckoutApiConfig
    _DIAL = {"IT": "+39", "FR": "+33", "DE": "+49", "ES": "+34", "NL": "+31", "BE": "+32",
             "AT": "+43", "PT": "+351", "IE": "+353", "CH": "+41", "GB": "+44", "US": "+1",
             "CA": "+1", "AU": "+61"}
    def _flag(cc):
        return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)
    api_cfg = CheckoutApiConfig.load()
    country = ""
    if form is not None:
        country = (form.initial.get("country") or getattr(form.instance, "country", "") or "")
    return {
        "phone_prefixes": [{"code": c, "dial": _DIAL.get(c, ""), "flag": _flag(c), "name": str(n)}
                            for c, n in COUNTRIES if _DIAL.get(c)],
        "prefill_prefix": "",
        "prefill_country": country,
        "checkout_api": api_cfg if (api_cfg and api_cfg.autocomplete_ready()) else None,
    }


def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            addr = form.save(commit=False)
            addr.user = request.user

            # if new default -> unset others
            if addr.is_default:
                Address.objects.filter(user=request.user, is_default=True).update(is_default=False)

            addr.save()
            messages.success(request, "Address saved.")
            return redirect("address_list")
    else:
        # smart defaults from Account
        form = AddressForm(initial={
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
            "phone": getattr(request.user, "phone_number", "") or "",
            "is_default": (Address.objects.filter(user=request.user).count() == 0),
        })

    ctx = {"form": form, "mode": "create"}; ctx.update(_address_form_extras(request, form))
    return render(request, "accounts/address_form.html", ctx)

@login_required(login_url="login")
def address_edit(request, address_id):
    addr = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == "POST":
        form = AddressForm(request.POST, instance=addr)
        if form.is_valid():
            addr = form.save(commit=False)

            if addr.is_default:
                Address.objects.filter(user=request.user, is_default=True).exclude(id=addr.id).update(is_default=False)

            addr.save()
            messages.success(request, "Address updated.")
            return redirect("address_list")
    else:
        form = AddressForm(instance=addr)

    ctx = {"form": form, "mode": "edit", "addr": addr}; ctx.update(_address_form_extras(request, form))
    return render(request, "accounts/address_form.html", ctx)

@login_required(login_url="login")
@require_POST
def address_delete(request, address_id):
    # Ownership-scoped + POST-only: a GET can no longer delete via link/prefetch/CSRF.
    addr = get_object_or_404(Address, id=address_id, user=request.user)
    was_default = addr.is_default
    addr.delete()

    # if default deleted -> make latest one default
    if was_default:
        next_addr = Address.objects.filter(user=request.user).order_by("-updated_at").first()
        if next_addr:
            next_addr.is_default = True
            next_addr.save(update_fields=["is_default"])

    messages.success(request, _("Address removed."))
    return redirect("address_list")

@login_required(login_url="login")
@require_POST
def address_set_default(request, address_id):
    addr = get_object_or_404(Address, id=address_id, user=request.user)
    Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
    addr.is_default = True
    addr.save(update_fields=["is_default"])
    messages.success(request, _("Default address updated."))
    return redirect("address_list")


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            phone_number = form.cleaned_data['phone_number']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            username = email.split("@")[0]
            user = Account.objects.create_user(first_name=first_name, last_name=last_name, email=email, username=username, password=password)
            user.phone_number = phone_number
            user.save()

            # USER ACTIVATION
            current_site = get_current_site(request)
            mail_subject = 'Please activate your account'
            message = render_to_string('accounts/account_verification_email.html', {
                'user': user,
                'domain': current_site,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': default_token_generator.make_token(user),
            })
            to_email = email
            send_email = EmailMessage(mail_subject, message, to=[to_email])
            send_email.send()
            # messages.success(request, 'Thank you for registering with us. We have sent you a verification email to your email address [rathan.kumar@gmail.com]. Please verify it.')
            return redirect('/accounts/login/?command=verification&email='+email)
    else:
        form = RegistrationForm()
    context = {
        'form': form,
    }
    return render(request, 'accounts/register.html', context)


def login(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']

        user = auth.authenticate(email=email, password=password)

        if user is not None:
            try:
                cart = Cart.objects.get(cart_id=_cart_id(request))
                is_cart_item_exists = CartItem.objects.filter(cart=cart).exists()
                if is_cart_item_exists:
                    cart_item = CartItem.objects.filter(cart=cart)

                    # Getting the product variations by cart id
                    product_variation = []
                    for item in cart_item:
                        variation = item.variations.all()
                        product_variation.append(list(variation))

                    # Get the cart items from the user to access his product variations
                    cart_item = CartItem.objects.filter(user=user)
                    ex_var_list = []
                    id = []
                    for item in cart_item:
                        existing_variation = item.variations.all()
                        ex_var_list.append(list(existing_variation))
                        id.append(item.id)

                    # product_variation = [1, 2, 3, 4, 6]
                    # ex_var_list = [4, 6, 3, 5]

                    for pr in product_variation:
                        if pr in ex_var_list:
                            index = ex_var_list.index(pr)
                            item_id = id[index]
                            item = CartItem.objects.get(id=item_id)
                            item.quantity += 1
                            item.user = user
                            item.save()
                        else:
                            cart_item = CartItem.objects.filter(cart=cart)
                            for item in cart_item:
                                item.user = user
                                item.save()
            except:
                pass
            _guest_sk = request.session.session_key
            auth.login(request, user)
            try:
                from wishlist.services import merge_session_to_user
                merge_session_to_user(request, user, session_key=_guest_sk)
            except Exception:
                pass
            messages.success(request, 'You are now logged in.')
            url = request.META.get('HTTP_REFERER')
            try:
                query = requests.utils.urlparse(url).query
                # next=/cart/checkout/
                params = dict(x.split('=') for x in query.split('&'))
                if 'next' in params:
                    nextPage = params['next']
                    return redirect(nextPage)                
            except:
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid login credentials')
            return redirect('login')
    return render(request, 'accounts/login.html')


@login_required(login_url = 'login')
def logout(request):
    auth.logout(request)
    messages.success(request, 'You are logged out.')
    return redirect('login')


def activate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except(TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Congratulations! Your account is activated.')
        return redirect('login')
    else:
        messages.error(request, 'Invalid activation link')
        return redirect('register')



def forgotPassword(request):
    if request.method == 'POST':
        email = request.POST['email']
        if Account.objects.filter(email=email).exists():
            user = Account.objects.get(email__exact=email)

            # Reset password email
            current_site = get_current_site(request)
            mail_subject = 'Reset Your Password'
            message = render_to_string('accounts/reset_password_email.html', {
                'user': user,
                'domain': current_site,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': default_token_generator.make_token(user),
            })
            to_email = email
            send_email = EmailMessage(mail_subject, message, to=[to_email])
            send_email.send()

            messages.success(request, 'Password reset email has been sent to your email address.')
            return redirect('login')
        else:
            messages.error(request, 'Account does not exist!')
            return redirect('forgotPassword')
    return render(request, 'accounts/forgotPassword.html')


def resetpassword_validate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except(TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        request.session['uid'] = uid
        messages.success(request, 'Please reset your password')
        return redirect('resetPassword')
    else:
        messages.error(request, 'This link has been expired!')
        return redirect('login')


def resetPassword(request):
    if request.method == 'POST':
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']

        if password == confirm_password:
            uid = request.session.get('uid')
            user = Account.objects.get(pk=uid)
            user.set_password(password)
            user.save()
            messages.success(request, 'Password reset successful')
            return redirect('login')
        else:
            messages.error(request, 'Password do not match!')
            return redirect('resetPassword')
    else:
        return render(request, 'accounts/resetPassword.html')

def staff_invite_accept(request, token):
    """Consume a staff invitation: the invitee sets their own password.

    The link is single-use and expiring. We never generated a password, so there
    is nothing to leak; an invalid, used or expired token says exactly that and
    goes nowhere near the account."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.utils import timezone

    from .models import StaffInvite

    invite = StaffInvite.objects.filter(token=token).select_related("account").first()
    if invite is None or not invite.is_usable:
        messages.error(request, _("This invitation link is no longer valid. "
                                  "Ask an administrator for a new one."))
        return redirect("login")

    if request.method != "POST":
        return render(request, "accounts/staff_invite.html", {"invite": invite})

    password1 = request.POST.get("new_password1") or ""
    password2 = request.POST.get("new_password2") or ""
    if not password1 or password1 != password2:
        messages.error(request, _("The two passwords didn't match."))
        return render(request, "accounts/staff_invite.html", {"invite": invite})
    try:
        validate_password(password1, invite.account)
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return render(request, "accounts/staff_invite.html", {"invite": invite})

    user = invite.account
    user.set_password(password1)
    user.is_active = True
    user.save()

    invite.accepted = True
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted", "accepted_at"])

    messages.success(request, _("Your admin account is ready — please sign in."))
    return redirect("login")
