from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
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
    from store.filters import apply_filters, build_facets, active_chips
    category = None
    base = Product.objects.filter(is_available=True)
    all_categories = Category.objects.all().order_by("category_name")

    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        base = base.filter(category=category)

    # Facets are computed from the category-scoped base (before color/size filters)
    # so options never vanish when selected.
    facets = build_facets(base)
    products_qs, active, sort = apply_filters(request, base)
    products_qs = products_qs.prefetch_related("gallery")
    count = products_qs.count()

    # active collection (for a compact hero/breadcrumb)
    active_collection = None
    if active.get("collection"):
        from merchandising.models import Collection
        active_collection = Collection.objects.filter(slug=active["collection"], is_active=True).first()

    # Analytics: distinguish a plain browse from a filtered/searched one.
    if active:
        _track_event(request, "filter_apply", {"n": str(len(active)),
                     "keys": ",".join(sorted(active.keys()))[:80]})
        if "keyword" in active:
            _track_event(request, "search_with_filters", {"q": active["keyword"][:60]})
        if count == 0:
            _track_event(request, "filter_no_results", {"keys": ",".join(sorted(active.keys()))[:80]})

    # No results with active filters -> show real recommendations to keep discovery alive.
    recommendations = []
    if count == 0 and active:
        try:
            from merchandising.recommendations import recommend_from_context
            recommendations = recommend_from_context(request, limit=4)
        except Exception:
            recommendations = list(Product.objects.filter(is_available=True)
                                   .order_by("-created_date")[:4])

    paginator = Paginator(products_qs, 9)
    paged_products = paginator.get_page(request.GET.get("page"))

    context = {
        "category": category,
        "categories": all_categories,
        "products": paged_products,
        "product_count": count,
        "sort": sort,
        "facets": facets,
        "active_filters": active,
        "active_chips": active_chips(active),
        "has_filters": bool(active),
        "active_collection": active_collection,
        "recommendations": recommendations,
        "querystring": request.GET.urlencode(),
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

    reviews = list(ReviewRating.objects.filter(product_id=single_product.id, status=True)
                   .select_related("user").order_by("-created_at"))
    # Verified purchase: the reviewer actually ordered this product.
    buyer_ids = set(OrderProduct.objects.filter(product_id=single_product.id, ordered=True)
                    .values_list("user_id", flat=True))
    for r in reviews:
        r.verified = r.user_id in buyer_ids
    # Rating summary + star distribution (approved reviews only, real data).
    review_count = len(reviews)
    review_avg = round(sum(r.rating for r in reviews) / review_count, 1) if review_count else 0
    dist = {s: 0 for s in (5, 4, 3, 2, 1)}
    for r in reviews:
        b = int(round(r.rating))
        if b in dist:
            dist[b] += 1
    review_dist = [{"stars": s, "count": dist[s],
                    "pct": int(dist[s] / review_count * 100) if review_count else 0}
                   for s in (5, 4, 3, 2, 1)]

    # Single-item shipping estimate for the detected country.
    from shipping.geo import detect_country
    from shipping.services import fallback_quote
    shipping_quote = fallback_quote(detect_country(request), total_quantity=1,
                                    subtotal=single_product.price)

    lang = (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]
    product_faqs = []
    try:
        from store.models import ProductFAQ
        product_faqs = [{"q": f.question_for(lang), "a": f.answer_for(lang)}
                        for f in ProductFAQ.for_product(single_product)[:8]]
    except Exception:
        pass

    # Recently viewed (session) — record THIS product, fetch the previous ones.
    from storefront.recently import record_view, get_recently_viewed
    recently_viewed = get_recently_viewed(request, exclude_id=single_product.id, limit=4)
    record_view(request, single_product.id)

    # "You may also like" — smart recommendations (curated → category → newest).
    complete_look, outfit = [], None
    try:
        from merchandising.recommendations import (recommend_for_product, complete_the_look,
                                                   outfits_for_product)
        related = recommend_for_product(single_product, limit=4)
        complete_look = complete_the_look(single_product, limit=6)
        outfits = outfits_for_product(single_product, limit=1)
        outfit = outfits[0] if outfits else None
    except Exception:
        related = list(Product.objects.filter(is_available=True, category=single_product.category)
                       .exclude(id=single_product.id).prefetch_related("gallery")[:4])
    if not related:
        related = list(Product.objects.filter(is_available=True)
                       .exclude(id=single_product.id).prefetch_related("gallery")[:4])

    context = {
        'single_product': single_product,
        'in_cart': in_cart,
        'orderproduct': orderproduct,
        'reviews': reviews,
        'review_count': review_count,
        'review_avg': review_avg,
        'review_dist': review_dist,
        'shipping_quote': shipping_quote,
        'related_products': related,
        'recently_viewed': recently_viewed,
        'product_faqs': product_faqs,
        'complete_look': complete_look,
        'outfit': outfit,
        'outfit_title': outfit.title_for(lang) if outfit else "",
        'outfit_desc': outfit.description_for(lang) if outfit else "",
        'outfit_products': list(outfit.active_products()) if outfit else [],
        'notify_me_enabled': single_product.stock <= 0 or not single_product.is_available,
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

    count = products.count()
    if keyword:
        _track_event(request, "search_query", {"q": keyword[:60]})
        if count == 0:
            _track_event(request, "search_no_results", {"q": keyword[:60]})

    paginator = Paginator(products, 9)
    page = request.GET.get("page")
    paged_products = paginator.get_page(page)

    context = {
        "categories": all_categories,   # ✅
        "products": paged_products,
        "product_count": count,
    }
    return render(request, "store/store.html", context)


def _track_event(request, name, meta=None):
    try:
        from storefront.models import AnalyticsEvent
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(name=name, path=request.path[:255],
                                      session_key=request.session.session_key or "", meta=meta or {})
    except Exception:
        pass


def autocomplete(request):
    """JSON product suggestions for the search bar. Sanitised, limited, no 500."""
    from django.http import JsonResponse
    q = (request.GET.get("q") or "").strip()[:60]
    if len(q) < 2:
        return JsonResponse({"query": q, "results": []})
    products = (Product.objects.filter(is_available=True)
                .filter(Q(product_name__icontains=q) | Q(description__icontains=q)
                        | Q(category__category_name__icontains=q))
                .select_related("category")[:6])
    sym = getattr(settings, "STORE_CURRENCY_SYMBOL", "€")
    results = [{
        "name": p.product_name,
        "url": p.get_url(),
        "price": f"{sym} {p.price}",
        "category": p.category.category_name if p.category_id else "",
        "image": p.cover_image() or "",
    } for p in products]
    return JsonResponse({"query": q, "results": results, "view_all": f"/store/search/?keyword={q}"})


def faq(request):
    """Site-wide General FAQ page, grouped by category and localised."""
    from collections import OrderedDict
    from django.utils.translation import gettext as _
    from store.models import GeneralFAQ
    lang = (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]
    # Translatable category labels (model choices are plain strings).
    cat_labels = {
        "shipping": _("Shipping & delivery"), "returns": _("Returns & refunds"),
        "payments": _("Payments & security"), "orders": _("Orders & tracking"),
        "account": _("Account & wishlist"), "sizing": _("Sizing & products"),
        "coupons": _("Coupons & offers"), "support": _("Support & assistant"),
    }
    groups = OrderedDict()
    for f in GeneralFAQ.objects.filter(is_active=True):
        groups.setdefault(f.category, {"label": cat_labels.get(f.category, f.category), "items": []})
        groups[f.category]["items"].append({"q": f.question_for(lang), "a": f.answer_for(lang)})
    return render(request, "store/faq.html", {"faq_groups": groups})


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
        existing = ReviewRating.objects.filter(user__id=request.user.id,
                                               product__id=product_id).first()
        form = ReviewForm(request.POST, instance=existing) if existing else ReviewForm(request.POST)
        if not form.is_valid():
            # Invalid rating (outside 1–5) or fields — fail gracefully, no 500.
            messages.error(request, 'Please give a rating between 1 and 5 and try again.')
            return redirect(url or 'store')
        if existing:
            form.save()
            messages.success(request, 'Thank you! Your review has been updated.')
            return redirect(url or 'store')
        data = ReviewRating()
        data.subject = form.cleaned_data['subject']
        data.rating = form.cleaned_data['rating']
        data.review = form.cleaned_data['review']
        data.ip = request.META.get('REMOTE_ADDR')
        data.product_id = product_id
        data.user_id = request.user.id
        data.save()
        messages.success(request, 'Thank you! Your review has been submitted.')
        return redirect(url or 'store')
    return redirect(url or 'store')