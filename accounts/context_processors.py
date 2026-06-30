"""Lazy portal counts for the account sidebar badges.

Each count is wrapped in SimpleLazyObject, so the COUNT query only runs when a template
actually reads it (i.e. the portal sidebar). Non-portal pages — store, home, PDP — never
trigger these queries even though the processor is global.
"""
from django.utils.functional import SimpleLazyObject


def portal_counts(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    def _orders():
        from orders.models import Order
        return Order.objects.filter(user=user, is_ordered=True).count()

    def _receipts():
        from orders.models import Order
        return Order.objects.filter(user=user, is_ordered=True, payment__isnull=False).count()

    def _addresses():
        from accounts.models import Address
        return Address.objects.filter(user=user).count()

    return {
        "PORTAL_ORDERS_COUNT": SimpleLazyObject(_orders),
        "PORTAL_RECEIPTS_COUNT": SimpleLazyObject(_receipts),
        "PORTAL_ADDRESSES_COUNT": SimpleLazyObject(_addresses),
    }
