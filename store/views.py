from django.shortcuts import render, get_object_or_404, redirect
from .models import Product, ReviewRating
from category.models import Category
from carts.models import CartItem
from django.db.models import Q

from carts.views import _cart_id
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from .forms import ReviewForm
from django.contrib import messages
from orders.models import OrderProduct


def store(request, category_slug=None):
    category = None
    products = Product.objects.filter(is_available=True)

    # Categories for sidebar
    all_categories = Category.objects.all().order_by("category_name")

    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)

    sort = request.GET.get("sort", "")
    if sort == "price_asc":
        products = products.order_by("price")
    elif sort == "price_desc":
        products = products.order_by("-price")
    elif sort == "name_asc":
        products = products.order_by("product_name")
    elif sort == "name_desc":
        products = products.order_by("-product_name")
    elif sort == "newest":
        products = products.order_by("-created_date")
    else:
        products = products.order_by("-created_date")

    paginator = Paginator(products, 9)
    page = request.GET.get("page")
    paged_products = paginator.get_page(page)

    context = {
        "category": category,
        "categories": all_categories,   # ✅ important
        "products": paged_products,
        "product_count": products.count(),
        "sort": sort,
    }
    return render(request, "store/store.html", context)

def product_detail(request, category_slug, product_slug):
    single_product = get_object_or_404(Product, category__slug=category_slug, slug=product_slug)

    if request.user.is_authenticated:
        in_cart = CartItem.objects.filter(user=request.user, product=single_product).exists()
        orderproduct = OrderProduct.objects.filter(
            user=request.user, product_id=single_product.id).exists()
    else:
        in_cart = CartItem.objects.filter(
            cart__cart_id=_cart_id(request), product=single_product).exists()
        orderproduct = None

    reviews = ReviewRating.objects.filter(product_id=single_product.id, status=True)

    # Single-item shipping estimate for the detected country.
    from shipping.geo import detect_country
    from shipping.services import fallback_quote
    shipping_quote = fallback_quote(detect_country(request), total_quantity=1,
                                    subtotal=single_product.price)

    context = {
        'single_product': single_product,
        'in_cart': in_cart,
        'orderproduct': orderproduct,
        'reviews': reviews,
        'shipping_quote': shipping_quote,
    }
    return render(request, 'store/product_detail.html', context)


def search(request):
    keyword = request.GET.get("keyword", "").strip()
    products = Product.objects.filter(is_available=True)

    all_categories = Category.objects.all().order_by("category_name")  # ✅

    if keyword:
        products = products.filter(
            Q(description__icontains=keyword) | Q(product_name__icontains=keyword)
        )

    products = products.order_by("-created_date")

    paginator = Paginator(products, 9)
    page = request.GET.get("page")
    paged_products = paginator.get_page(page)

    context = {
        "categories": all_categories,   # ✅
        "products": paged_products,
        "product_count": products.count(),
    }
    return render(request, "store/store.html", context)


def submit_review(request, product_id):
    url = request.META.get('HTTP_REFERER')
    if not request.user.is_authenticated:
        messages.error(request, 'Please sign in to write a review.')
        return redirect('login')
    # Only verified buyers may review.
    if not OrderProduct.objects.filter(user=request.user, product_id=product_id, ordered=True).exists():
        messages.error(request, 'Only verified buyers can review this product.')
        return redirect(url or 'store')
    if request.method == 'POST':
        try:
            reviews = ReviewRating.objects.get(user__id=request.user.id, product__id=product_id)
            form = ReviewForm(request.POST, instance=reviews)
            form.save()
            messages.success(request, 'Thank you! Your review has been updated.')
            return redirect(url)
        except ReviewRating.DoesNotExist:
            form = ReviewForm(request.POST)
            if form.is_valid():
                data = ReviewRating()
                data.subject = form.cleaned_data['subject']
                data.rating = form.cleaned_data['rating']
                data.review = form.cleaned_data['review']
                data.ip = request.META.get('REMOTE_ADDR')
                data.product_id = product_id
                data.user_id = request.user.id
                data.save()
                messages.success(request, 'Thank you! Your review has been submitted.')
                return redirect(url)