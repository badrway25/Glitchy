"""Session-based 'recently viewed' products (no DB writes, no PII)."""
SESSION_KEY = "recently_viewed"
MAX_STORED = 10


def record_view(request, product_id):
    rv = [pid for pid in request.session.get(SESSION_KEY, []) if pid != product_id]
    rv.insert(0, product_id)
    request.session[SESSION_KEY] = rv[:MAX_STORED]
    request.session.modified = True


def get_recently_viewed(request, exclude_id=None, limit=4):
    from store.models import Product
    ids = [pid for pid in request.session.get(SESSION_KEY, []) if pid != exclude_id]
    if not ids:
        return []
    by_id = {p.id: p for p in
             Product.objects.filter(id__in=ids, is_available=True).select_related("category")}
    return [by_id[i] for i in ids if i in by_id][:limit]
