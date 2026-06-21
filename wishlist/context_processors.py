"""Expose wishlist count + the set of wishlisted product ids to templates."""
from . import services


def wishlist_globals(request):
    try:
        return {
            "WISHLIST_COUNT": services.count(request),
            "WISHLIST_IDS": services.wishlisted_ids(request),
        }
    except Exception:
        return {"WISHLIST_COUNT": 0, "WISHLIST_IDS": set()}
