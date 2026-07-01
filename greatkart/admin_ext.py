"""Unfold admin extensions — environment badge + e-commerce dashboard KPIs.

All queries are aggregate counts (no N+1). No secrets, no PII. The dashboard reads real
catalog/order state so operators can spot gaps (missing images/prices, stale sync, errors).
"""
import os

from django.conf import settings
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone


def environment_callback(request):
    """Return [label, color] for the Unfold environment badge."""
    env = (os.environ.get("APP_ENVIRONMENT") or "").strip().lower()
    if not env:
        env = "local" if getattr(settings, "DEBUG", False) else "production"
    return {
        "local": ["Local", "warning"],
        "staging": ["Staging", "info"],
        "production": ["Production", "danger"],
    }.get(env, ["Local", "warning"])


def _safe_url(viewname, *args):
    try:
        return reverse(viewname, args=args)
    except Exception:
        return "#"


def catalog_kpis():
    """Aggregate catalog/commerce KPIs (no N+1, no PII, no secrets)."""
    from store.models import Product

    qs = Product.objects.all()
    stale_before = timezone.now() - timezone.timedelta(
        minutes=getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360))

    total = qs.count()
    printify = qs.exclude(printify_product_id__isnull=True).exclude(printify_product_id="").count()
    no_image = (qs.annotate(_g=Count("gallery"))
                  .filter(_g=0).filter(Q(images="") | Q(images__isnull=True)).count())
    missing_price = qs.filter(Q(price__isnull=True) | Q(price__lte=0)).count()
    missing_category = qs.filter(category__isnull=True).count()
    stale_sync = qs.filter(printify_product_id__isnull=False,
                           printify_synced_at__lt=stale_before).count()
    sync_errors = qs.filter(printify_sync_status="error").count()

    kpis = [
        {"label": "Products", "value": total, "url": _safe_url("admin:store_product_changelist")},
        {"label": "Active", "value": qs.filter(is_available=True).count(),
         "url": _safe_url("admin:store_product_changelist") + "?is_available__exact=1"},
        {"label": "Printify", "value": printify,
         "url": _safe_url("admin:store_product_changelist") + "?printify=1"},
        {"label": "Synced", "value": qs.filter(printify_sync_status="synced").count(),
         "url": _safe_url("admin:store_product_changelist") + "?printify_sync_status__exact=synced"},
        {"label": "Missing image", "value": no_image, "tone": ("danger" if no_image else "ok"),
         "url": _safe_url("admin:store_product_changelist") + "?missing_image=1"},
        {"label": "Missing price", "value": missing_price, "tone": ("danger" if missing_price else "ok"),
         "url": _safe_url("admin:store_product_changelist") + "?missing_price=1"},
        {"label": "Missing category", "value": missing_category, "tone": ("danger" if missing_category else "ok"),
         "url": _safe_url("admin:store_product_changelist")},
        {"label": "Stale sync", "value": stale_sync, "tone": ("warning" if stale_sync else "ok"),
         "url": _safe_url("admin:store_product_changelist") + "?stale_sync=1"},
        {"label": "Sync errors", "value": sync_errors, "tone": ("danger" if sync_errors else "ok"),
         "url": _safe_url("admin:store_product_changelist") + "?printify_sync_status__exact=error"},
    ]
    return kpis


def _commerce_kpis():
    from orders.models import Order
    try:
        from wishlist.models import WishlistItem as _W
        wish = _W.objects.count()
    except Exception:
        wish = None
    recent = timezone.now() - timezone.timedelta(days=30)
    out = [
        {"label": "Orders", "value": Order.objects.count(), "url": _safe_url("admin:orders_order_changelist")},
        {"label": "Orders (30d)", "value": Order.objects.filter(created_at__gte=recent).count(),
         "url": _safe_url("admin:orders_order_changelist")},
    ]
    if wish is not None:
        out.append({"label": "Wishlist items", "value": wish})
    return out


def dashboard_callback(request, context):
    """Inject KPI cards + quick links into the Unfold dashboard context."""
    try:
        context["gl_catalog_kpis"] = catalog_kpis()
        context["gl_commerce_kpis"] = _commerce_kpis()
    except Exception:
        # never break the admin index over a KPI query
        context["gl_catalog_kpis"] = []
        context["gl_commerce_kpis"] = []
    context["gl_quick_actions"] = [
        {"label": "Printify accounts", "icon": "vpn_key", "url": _safe_url("admin:printify_integration_printifyaccountconfig_changelist")},
        {"label": "Sync monitor", "icon": "sync", "url": _safe_url("admin:printify_integration_printifysyncstate_changelist")},
        {"label": "Catalog health", "icon": "health_and_safety", "url": _safe_url("admin:store_product_changelist") + "?missing_image=1"},
        {"label": "Orders", "icon": "receipt_long", "url": _safe_url("admin:orders_order_changelist")},
    ]
    return context
