"""Merchandising pages & endpoints: collections, style quiz, notify-me, outfit add."""
import hashlib
import json

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import Collection, Outfit, ProductNotificationSignup


def _lang(request):
    return (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]


def track(request, name, meta=None):
    try:
        from storefront.models import AnalyticsEvent
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(name=name, path=request.path[:255],
                                      session_key=request.session.session_key or "",
                                      meta=meta or {})
    except Exception:
        pass


def _dispatch(event, payload):
    """Best-effort n8n growth event — never raises, never blocks, no 500."""
    try:
        from notifications.dispatcher import dispatch_event
        from notifications.email_settings import get_admin_notify_email
        dispatch_event(event, payload,
                       recipient_email=get_admin_notify_email() or "")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #
def collections_index(request):
    lang = _lang(request)
    qs = Collection.objects.filter(is_active=True).prefetch_related("products")

    def _card(c):
        prods = c.active_products()
        return {
            "obj": c, "url": c.get_url(), "name": c.name,
            "subtitle": c.subtitle_for(lang), "image": c.image,
            "count": len(prods), "featured": c.featured,
            "previews": [p for p in prods[:4]],   # small thumbnails for the card
        }

    all_cards = [_card(c) for c in qs]

    # Shop by mood / season — only buckets with at least one real, non-empty collection.
    mood_map = dict(Collection.MOOD_CHOICES)
    season_map = dict(Collection.SEASON_CHOICES)

    def _buckets(attr, choices):
        out = []
        for key, label in choices:
            n = sum(1 for c in all_cards if getattr(c["obj"], attr) == key and c["count"])
            if n:
                out.append({"key": key, "label": label, "count": n})
        return out

    moods = _buckets("mood", Collection.MOOD_CHOICES)
    seasons = _buckets("season", Collection.SEASON_CHOICES)

    # Active filter (real, validated key only) -> a true filtered landing.
    f_mood = request.GET.get("mood", "")
    f_season = request.GET.get("season", "")
    active_filter = None
    cards = all_cards
    if f_mood in mood_map and any(b["key"] == f_mood for b in moods):
        cards = [c for c in all_cards if c["obj"].mood == f_mood]
        active_filter = {"type": "mood", "key": f_mood, "label": mood_map[f_mood]}
    elif f_season in season_map and any(b["key"] == f_season for b in seasons):
        cards = [c for c in all_cards if c["obj"].season == f_season]
        active_filter = {"type": "season", "key": f_season, "label": season_map[f_season]}

    featured = [] if active_filter else [c for c in all_cards if c["featured"] and c["count"]][:3]
    total_products = sum(c["count"] for c in cards)

    return render(request, "merchandising/collections_index.html", {
        "cards": cards,
        "featured": featured,
        "collection_count": len(cards),
        "total_products": total_products,
        "moods": moods,
        "seasons": seasons,
        "active_filter": active_filter,
        "ai_enabled": getattr(settings, "AI_ASSISTANT_ENABLED", False),
    })


def collection_detail(request, slug):
    collection = get_object_or_404(Collection, slug=slug, is_active=True)
    lang = _lang(request)
    track(request, "collection_view", {"slug": slug})

    products = list(collection.active_products().prefetch_related("gallery"))
    sort = request.GET.get("sort", "")
    if sort == "price_asc":
        products.sort(key=lambda p: float(p.price or 0))
    elif sort == "price_desc":
        products.sort(key=lambda p: float(p.price or 0), reverse=True)
    elif sort == "newest":
        products.sort(key=lambda p: p.created_date or 0, reverse=True)

    pr = collection.price_range()
    return render(request, "merchandising/collection.html", {
        "collection": collection,
        "products": products,
        "product_count": len(products),
        "hero_title": collection.hero_title_for(lang),
        "subtitle": collection.subtitle_for(lang),
        "editorial": collection.editorial_intro_for(lang),
        "mood_label": collection.get_mood_display() if collection.mood else "",
        "season_label": collection.get_season_display() if collection.season else "",
        "colors": collection.main_colors(),
        "price_min": pr[0] if pr else None,
        "price_max": pr[1] if pr else None,
        "related": collection.related(limit=3),
        "sort": sort,
    })


# --------------------------------------------------------------------------- #
# Style quiz (catalog-based, no sensitive data)
# --------------------------------------------------------------------------- #
QUIZ_QUESTIONS = [
    {"key": "category", "options": ["any"]},  # filled from real categories in the view
    {"key": "budget", "options": ["under_25", "25_50", "50_100", "over_100"]},
    {"key": "vibe", "options": ["minimal", "elegant", "casual", "bold"]},
    {"key": "color", "options": ["neutral", "blue", "black", "white", "any"]},
    {"key": "occasion", "options": ["everyday", "work", "going_out", "gift"]},
]
_BUDGET = {"under_25": (0, 25), "25_50": (25, 50), "50_100": (50, 100), "over_100": (100, 10 ** 6)}


def style_quiz(request):
    from category.models import Category
    if request.method == "POST":
        return _quiz_results(request)
    track(request, "style_quiz_start", {})
    return render(request, "merchandising/style_quiz.html",
                  {"categories": Category.objects.all().order_by("category_name")})


def _quiz_results(request):
    from store.models import Product
    cat = (request.POST.get("category") or "any")[:60]
    budget = (request.POST.get("budget") or "")[:20]
    color = (request.POST.get("color") or "any")[:20]

    qs = Product.objects.filter(is_available=True)
    if cat and cat != "any":
        qs = qs.filter(category__slug=cat)
    if budget in _BUDGET:
        lo, hi = _BUDGET[budget]
        qs = qs.filter(price__gte=lo, price__lt=hi)
    if color and color != "any":
        qs = qs.filter(variation__variation_category="color",
                       variation__variation_value__icontains=color).distinct()

    products = list(qs.order_by("-created_date")[:8])
    fallback = False
    if len(products) < 3:   # controlled fallback to best/newest
        fallback = True
        extra = Product.objects.filter(is_available=True).exclude(
            id__in=[p.id for p in products]).order_by("-created_date")[:8 - len(products)]
        products += list(extra)

    request.session["style_quiz"] = {"category": cat, "budget": budget, "color": color}
    request.session.modified = True
    track(request, "style_quiz_complete", {"category": cat, "budget": budget, "fallback": fallback})
    _dispatch("style_quiz_completed", {"category": cat, "budget": budget, "color": color})
    return render(request, "merchandising/style_quiz_results.html",
                  {"products": products, "fallback": fallback,
                   "prefs": request.session["style_quiz"]})


# --------------------------------------------------------------------------- #
# Notify me (back-in-stock / new drop)
# --------------------------------------------------------------------------- #
def _hash_ip(request):
    ip = request.META.get("REMOTE_ADDR", "")
    salt = getattr(settings, "SECRET_KEY", "")[:16]
    return hashlib.sha256((salt + ip).encode()).hexdigest() if ip else ""


def _rate_limited(request, key="notify", limit=5, window=3600):
    now = timezone.now().timestamp()
    bucket = request.session.get(f"_rl_{key}", [])
    bucket = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    request.session[f"_rl_{key}"] = bucket
    request.session.modified = True
    return False


@require_POST
def notify_me(request):
    # Honeypot: real users never fill this hidden field.
    if (request.POST.get("website") or "").strip():
        return JsonResponse({"ok": True})   # silently swallow bots
    email = (request.POST.get("email") or "").strip()[:254]
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"ok": False, "error": "invalid_email"}, status=400)
    if not request.POST.get("consent"):
        return JsonResponse({"ok": False, "error": "consent_required"}, status=400)
    if _rate_limited(request):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)

    notify_type = request.POST.get("notify_type", "back_in_stock")
    if notify_type not in dict(ProductNotificationSignup.TYPE_CHOICES):
        notify_type = "back_in_stock"
    product = None
    pid = request.POST.get("product_id")
    if pid:
        from store.models import Product
        product = Product.objects.filter(id=pid).first()

    ProductNotificationSignup.objects.create(
        email=email, product=product, variant=(request.POST.get("variant") or "")[:80],
        notify_type=notify_type, consent=True, ip_hash=_hash_ip(request))
    track(request, "notification_signup", {"type": notify_type, "pid": str(pid or "")})
    _dispatch("product_notification_signup",
              {"email": email, "type": notify_type,
               "product": product.product_name if product else ""})
    return JsonResponse({"ok": True, "message": _("We'll email you — no spam, promise.")})


# --------------------------------------------------------------------------- #
# Outfit: add selected products to cart
# --------------------------------------------------------------------------- #
@require_POST
def outfit_add(request):
    try:
        ids = json.loads(request.body or "{}").get("product_ids", [])
        ids = [int(x) for x in ids][:12]
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "bad_request"}, status=400)
    if not ids:
        return JsonResponse({"ok": False, "error": "empty"}, status=400)

    from store.models import Product
    from carts.models import Cart, CartItem
    added = 0
    products = Product.objects.filter(id__in=ids, is_available=True)
    if request.user.is_authenticated:
        for p in products:
            CartItem.objects.create(user=request.user, product=p, quantity=1, is_active=True)
            added += 1
    else:
        if not request.session.session_key:
            request.session.save()
        cart, _c = Cart.objects.get_or_create(cart_id=request.session.session_key)
        for p in products:
            CartItem.objects.create(cart=cart, product=p, quantity=1, is_active=True)
            added += 1
    track(request, "outfit_add_to_cart", {"count": str(added)})
    _dispatch("outfit_add_to_cart", {"count": added})
    return JsonResponse({"ok": True, "added": added})
