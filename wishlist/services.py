"""Wishlist helpers shared by views, context processor and templates."""
from .models import WishlistItem


def _ensure_session(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _scope(request):
    """Return (kwargs, defaults) identifying the current owner (user or guest)."""
    if request.user.is_authenticated:
        return {"user": request.user}
    return {"user": None, "session_key": _ensure_session(request)}


def items(request, saved_for_later=None):
    qs = WishlistItem.objects.filter(**_scope(request)).select_related("product", "product__category")
    if saved_for_later is not None:
        qs = qs.filter(saved_for_later=saved_for_later)
    return qs


def count(request):
    return WishlistItem.objects.filter(**_scope(request)).count()


def wishlisted_ids(request):
    return set(WishlistItem.objects.filter(**_scope(request)).values_list("product_id", flat=True))


def is_wishlisted(request, product_id):
    return WishlistItem.objects.filter(product_id=product_id, **_scope(request)).exists()


def add(request, product_id, saved_for_later=False):
    obj, created = WishlistItem.objects.get_or_create(
        product_id=product_id, **_scope(request),
        defaults={"saved_for_later": saved_for_later})
    if not created and saved_for_later and not obj.saved_for_later:
        obj.saved_for_later = True
        obj.save(update_fields=["saved_for_later"])
    return obj, created


def remove(request, product_id):
    return WishlistItem.objects.filter(product_id=product_id, **_scope(request)).delete()[0]


def toggle(request, product_id):
    if is_wishlisted(request, product_id):
        remove(request, product_id)
        return False
    add(request, product_id)
    return True


def merge_session_to_user(request, user, session_key=None):
    """Move guest wishlist rows to the user's account on login (no duplicates).
    Pass the PRE-login session key (auth.login cycles the key)."""
    sk = session_key or request.session.session_key
    if not sk:
        return
    owned = set(WishlistItem.objects.filter(user=user).values_list("product_id", flat=True))
    for item in WishlistItem.objects.filter(user__isnull=True, session_key=sk):
        if item.product_id in owned:
            item.delete()
        else:
            item.user = user
            item.session_key = ""
            item.save(update_fields=["user", "session_key"])
