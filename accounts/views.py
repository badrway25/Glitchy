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

from django.db.models import Sum,Q

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


@login_required(login_url='login')
def dashboard(request):
    user = request.user

    orders_qs = Order.objects.filter(user=user, is_ordered=True).order_by('-created_at')

    total_orders = orders_qs.count()
    total_spent = orders_qs.aggregate(total=Sum("order_total"))["total"] or 0

    pending_count = orders_qs.filter(status__in=["New", "Accepted"]).count()
    completed_count = orders_qs.filter(status="Completed").count()
    cancelled_count = orders_qs.filter(status="Cancelled").count()

    recent_orders = orders_qs[:5]

    context = {
        "orders": recent_orders,
        "total_orders": total_orders,
        "total_spent": total_spent,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required(login_url='login')
def my_orders(request):
    user = request.user
    orders_qs = Order.objects.filter(user=user, is_ordered=True).order_by('-created_at')

    paginator = Paginator(orders_qs, 10)
    page = request.GET.get("page")
    orders = paginator.get_page(page)

    context = {
        "orders": orders,
    }
    return render(request, "accounts/my_orders.html", context)


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
    addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-updated_at")
    return render(request, "accounts/address_list.html", {"addresses": addresses})

@login_required(login_url="login")
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

    return render(request, "accounts/address_form.html", {"form": form, "mode": "create"})

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

    return render(request, "accounts/address_form.html", {"form": form, "mode": "edit", "addr": addr})

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