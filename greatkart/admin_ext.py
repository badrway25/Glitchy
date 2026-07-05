"""Unfold admin extensions — environment badge + visual-analytics dashboard.

Everything here is aggregate/derived: no N+1 (counts + a couple of grouped queries), no
secrets, and no PII (orders are counted, never listed; product names/slugs are public). The
dashboard_callback returns plain data structures; the SVG/CSS charts are rendered in
templates/admin/index.html with no external/CDN dependency.
"""
import os

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# --- brand chart palette (kept in sync with the admin CSS) ------------------
C_GOLD = "#a6824c"
C_EMERALD = "#3f7d63"
C_AMBER = "#c08a3e"
C_RUBY = "#b3554e"
C_INK = "#3a352c"
C_MUTED = "#9c948a"


def environment_callback(request):
    env = (os.environ.get("APP_ENVIRONMENT") or "").strip().lower()
    if not env:
        env = "local" if getattr(settings, "DEBUG", False) else "production"
    return {
        "local": [_("Local"), "warning"],
        "staging": [_("Staging"), "info"],
        "production": [_("Production"), "danger"],
    }.get(env, [_("Local"), "warning"])


def _safe_url(viewname, *args):
    try:
        return reverse(viewname, args=args)
    except Exception:
        return "#"


def _pl(base):
    return _safe_url("admin:store_product_changelist") + base


def _pct(part, whole):
    return round(100 * part / whole) if whole else 0


def _conic(segments):
    """Build a CSS conic-gradient string from [(color, value), ...]. Deterministic."""
    total = sum(v for _c, v in segments) or 1
    stops, acc = [], 0.0
    for color, value in segments:
        start = acc / total * 100
        acc += value
        end = acc / total * 100
        stops.append("%s %.2f%% %.2f%%" % (color, start, end))
    return "conic-gradient(%s)" % ", ".join(stops)


def catalog_health():
    """Score 0-100 + per-dimension 'ok %' bars. Reads aggregate counts only."""
    from store.models import Product

    qs = Product.objects.all()
    total = qs.count()
    if not total:
        return {"score": 100, "total": 0, "dimensions": [], "issues": []}

    cutoff = timezone.now() - timezone.timedelta(
        minutes=getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360))

    no_image = (qs.annotate(_g=Count("gallery")).filter(_g=0)
                  .filter(Q(images="") | Q(images__isnull=True)).count())
    no_price = qs.filter(Q(price__isnull=True) | Q(price__lte=0)).count()
    no_cat = qs.filter(category__isnull=True).count()
    no_desc = qs.filter(Q(description="") | Q(description__isnull=True)).count()
    no_var = qs.annotate(_v=Count("variation")).filter(_v=0).count()
    stale = qs.filter(printify_product_id__isnull=False, printify_synced_at__lt=cutoff).count()
    errors = qs.filter(printify_sync_status="error").count()

    raw = [
        ("Images", no_image, "sev-crit", _pl("?missing_image=1")),
        ("Prices", no_price, "sev-crit", _pl("?missing_price=1")),
        ("Categories", no_cat, "sev-crit", _pl("")),
        ("Descriptions", no_desc, "sev-warn", _pl("")),
        ("Variants", no_var, "sev-warn", _pl("")),
        ("Sync freshness", stale, "sev-warn", _pl("?stale_sync=1")),
        ("Sync errors", errors, "sev-crit", _pl("?printify_sync_status__exact=error")),
    ]
    dimensions = [{"label": lbl, "bad": bad, "ok_pct": _pct(total - bad, total),
                   "sev": sev, "url": url} for lbl, bad, sev, url in raw]
    score = round(sum(d["ok_pct"] for d in dimensions) / len(dimensions))
    issues = [{"label": lbl, "count": bad, "sev": sev, "url": url}
              for lbl, bad, sev, url in raw if bad]
    issues.sort(key=lambda i: (i["sev"] != "sev-crit", -i["count"]))
    # SVG ring geometry (r=52) so the arc renders correctly with NO JS (progressive enhancement)
    import math
    circ = 2 * math.pi * 52
    tone = "is-good" if score >= 85 else ("is-warn" if score >= 60 else "is-bad")
    return {"score": score, "total": total, "dimensions": dimensions, "issues": issues,
            "ring_circ": round(circ, 1), "ring_offset": round(circ * (1 - score / 100), 1),
            "tone": tone}


def product_status():
    """Active/inactive + Printify/manual distributions for donut charts."""
    from store.models import Product

    qs = Product.objects.all()
    total = qs.count()
    active = qs.filter(is_available=True).count()
    printify = qs.exclude(printify_product_id__isnull=True).exclude(printify_product_id="").count()
    synced = qs.filter(printify_sync_status="synced").count()
    availability = [
        {"label": "Active", "value": active, "color": C_EMERALD, "url": _pl("?is_available__exact=1")},
        {"label": "Hidden", "value": total - active, "color": C_MUTED, "url": _pl("?is_available__exact=0")},
    ]
    source = [
        {"label": "Printify", "value": printify, "color": C_GOLD, "url": _pl("?printify=1")},
        {"label": "Manual", "value": total - printify, "color": C_INK, "url": _pl("?printify=0")},
    ]
    return {
        "total": total, "synced": synced,
        "availability": availability, "availability_conic": _conic([(s["color"], s["value"]) for s in availability]),
        "source": source, "source_conic": _conic([(s["color"], s["value"]) for s in source]),
    }


def sync_health():
    """Safe snapshot of the Printify sync daemon (no token, no PII)."""
    out = {"configured": False, "enabled": False, "mode": "—", "token_present": False,
           "shop_id": "—", "last_check": None, "connection": "unknown",
           "stale_products": 0, "sync_errors": 0, "backoff": False, "locked": False,
           "publish_off": True, "orders_off": True}
    try:
        from printify_integration.sync_daemon import status_snapshot
        snap = status_snapshot()
        out["enabled"] = bool(snap.get("enabled"))
        out["stale_products"] = snap.get("stale_products", 0)
        out["backoff"] = bool(snap.get("backoff_active"))
    except Exception:
        pass
    try:
        from printify_integration.models import PrintifyAccountConfig
        cfg = PrintifyAccountConfig.active()
        if cfg:
            out.update({
                "configured": True, "mode": cfg.get_sync_mode_display(),
                "token_present": cfg.has_token(), "shop_id": cfg.shop_id or "—",
                "last_check": cfg.last_connection_check_at,
                "connection": cfg.last_connection_status or "unknown",
                "publish_off": not cfg.allow_product_publish,
                "orders_off": not cfg.allow_order_creation,
                "enabled": out["enabled"] or cfg.sync_enabled,
            })
    except Exception:
        pass
    try:
        from store.models import Product
        out["sync_errors"] = Product.objects.filter(printify_sync_status="error").count()
    except Exception:
        pass
    return out


def orders_snapshot():
    """Counts + totals for the last 7/30 days. No PII (never lists an order)."""
    try:
        from orders.models import Order
    except Exception:
        return {"available": False}
    now = timezone.now()
    d7, d30 = now - timezone.timedelta(days=7), now - timezone.timedelta(days=30)
    paid = Order.objects.filter(is_ordered=True)
    # 7-day daily counts for a mini bar sparkline
    days = []
    for i in range(6, -1, -1):
        day = (now - timezone.timedelta(days=i))
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timezone.timedelta(days=1)
        days.append({"label": start.strftime("%a"),
                     "count": paid.filter(created_at__gte=start, created_at__lt=end).count()})
    maxc = max([d["count"] for d in days] + [1])
    for d in days:
        d["h_pct"] = _pct(d["count"], maxc)
    total30 = paid.filter(created_at__gte=d30).aggregate(
        n=Count("id"), amt=Sum("order_total"))
    return {
        "available": True,
        "count_7d": paid.filter(created_at__gte=d7).count(),
        "count_30d": total30["n"] or 0,
        "amount_30d": round(float(total30["amt"] or 0), 2),
        "currency": getattr(settings, "STORE_CURRENCY", "EUR"),
        "days": days,
        "url": _safe_url("admin:orders_order_changelist"),
    }


def wishlist_signal():
    try:
        from wishlist.models import WishlistItem
        from store.models import Product
    except Exception:
        return {"available": False}
    total = WishlistItem.objects.count()
    top = (Product.objects.annotate(_w=Count("wishlisted_by"))
           .filter(_w__gt=0).order_by("-_w")[:5])
    return {"available": True, "total": total,
            "top": [{"name": p.product_name[:40], "count": getattr(p, "_w", 0),
                     "url": _safe_url("admin:store_product_change", p.id)} for p in top]}


def category_readiness():
    """Per top category: product count + a readiness % (share with an image + price)."""
    from store.models import Product, Category

    rows = []
    cats = (Category.objects.annotate(_n=Count("product")).filter(_n__gt=0)
            .order_by("-_n")[:6])
    for c in cats:
        pqs = Product.objects.filter(category=c)
        n = pqs.count()
        bad = (pqs.annotate(_g=Count("gallery")).filter(
            Q(_g=0) & (Q(images="") | Q(images__isnull=True))).count()
            + pqs.filter(Q(price__isnull=True) | Q(price__lte=0)).count())
        ready = _pct(max(n - bad, 0), n)
        rows.append({"name": c.category_name, "count": n, "ready_pct": ready,
                     "url": _pl("?category__id__exact=%d" % c.id)})
    return rows


def payments_snapshot():
    """Aggregated payment KPIs — counts + sums only, never a card/id/PII."""
    try:
        from django.db.models import Sum, Count
        from orders.models import Order, Payment
    except Exception:
        return {"available": False}
    now = timezone.now()
    d1 = now - timezone.timedelta(days=1)
    d7 = now - timezone.timedelta(days=7)
    paid = Order.objects.filter(is_ordered=True)
    by_method = list(Payment.objects.filter(created_at__gte=d7)
                     .values("payment_method").annotate(n=Count("id")).order_by("-n")[:4])
    return {
        "available": True,
        "today": paid.filter(created_at__gte=d1).count(),
        "revenue_7d": round(paid.filter(created_at__gte=d7)
                            .aggregate(s=Sum("order_total"))["s"] or 0, 2),
        "pending": Order.objects.filter(is_ordered=False,
                                        created_at__gte=d7).count(),
        "by_method": by_method,
    }


def outbox_snapshot():
    """n8n/email outbox health — status counts + config flag, zero recipients shown."""
    try:
        from django.conf import settings as st
        from django.db.models import Count
        from notifications.models import OutboundEvent
    except Exception:
        return {"available": False}
    d7 = timezone.now() - timezone.timedelta(days=7)
    counts = {r["status"]: r["n"] for r in
              OutboundEvent.objects.filter(created_at__gte=d7)
              .values("status").annotate(n=Count("id"))}
    return {
        "available": True,
        "n8n_enabled": bool(getattr(st, "N8N_ENABLED", False)),
        "sent": counts.get("sent", 0),
        "pending": counts.get("pending", 0) + counts.get("skipped", 0),
        "failed": counts.get("failed", 0),
    }


def assistant_snapshot():
    """Assistant status — config + 24h volume, no message content."""
    try:
        from assistant.models import AssistantConfig, AssistantMessage
        from assistant.providers import OpenAIProvider
    except Exception:
        return {"available": False}
    cfg = AssistantConfig.load()
    d1 = timezone.now() - timezone.timedelta(hours=24)
    msgs = AssistantMessage.objects.filter(created_at__gte=d1)
    return {
        "available": True,
        "online": OpenAIProvider().available(),
        "enabled": bool(cfg and cfg.is_enabled),
        "key_set": bool(cfg and cfg.has_api_key()),
        "model": (cfg.model if cfg else ""),
        "msgs_24h": msgs.filter(role="user").count(),
        "blocked_24h": msgs.filter(role="assistant",
                                   provider="guardrail").count(),
    }


def ops_health():
    """Configured yes/no per provider — flags only, never a key."""
    out = []
    try:
        from payments import config as pconf
        out.append(("Stripe", bool(pconf.stripe_secret_key() and pconf.stripe_publishable_key())))
        out.append(("PayPal", pconf.paypal_available()))
    except Exception:
        pass
    try:
        from shipping.models import CheckoutApiConfig
        c = CheckoutApiConfig.load()
        out.append(("Google Places", bool(c and c.autocomplete_ready())))
    except Exception:
        pass
    try:
        from assistant.models import AssistantConfig
        a = AssistantConfig.load()
        out.append(("OpenAI", bool(a and a.is_enabled and a.has_api_key())))
    except Exception:
        pass
    try:
        from django.conf import settings as st
        out.append(("n8n", bool(getattr(st, "N8N_ENABLED", False))))
    except Exception:
        pass
    return out


def recent_activity(limit=6):
    """Latest paid orders — number/status/total only (no names, no addresses)."""
    try:
        from orders.models import Order
        rows = list(Order.objects.filter(is_ordered=True)
                    .order_by("-created_at")
                    .values("order_number", "status", "order_total", "created_at",
                            "printify_status")[:limit])
        return rows
    except Exception:
        return []


def dashboard_callback(request, context):
    try:
        context["gl_health"] = catalog_health()
        context["gl_status"] = product_status()
        context["gl_sync"] = sync_health()
        context["gl_orders"] = orders_snapshot()
        context["gl_wishlist"] = wishlist_signal()
        context["gl_categories"] = category_readiness()
        context["gl_payments"] = payments_snapshot()
        context["gl_outbox"] = outbox_snapshot()
        context["gl_assistant"] = assistant_snapshot()
        context["gl_ops_health"] = ops_health()
        context["gl_recent"] = recent_activity()
    except Exception:
        for k in ("gl_health", "gl_status", "gl_sync", "gl_orders", "gl_wishlist", "gl_categories",
                  "gl_payments", "gl_outbox", "gl_assistant", "gl_ops_health", "gl_recent"):
            context.setdefault(k, None)
    context["gl_quick_actions"] = [
        {"label": "Printify accounts", "url": _safe_url("admin:printify_integration_printifyaccountconfig_changelist")},
        {"label": "Sync monitor", "url": _safe_url("admin:printify_integration_printifysyncstate_changelist")},
        {"label": "Missing images", "url": _pl("?missing_image=1")},
        {"label": "Missing prices", "url": _pl("?missing_price=1")},
        {"label": "Orders", "url": _safe_url("admin:orders_order_changelist")},
        {"label": "Payments config", "url": _safe_url("admin:payments_paymentproviderconfig_changelist")},
        {"label": "Assistant settings", "url": _safe_url("admin:assistant_assistantconfig_changelist")},
        {"label": "Email outbox", "url": _safe_url("admin:notifications_outboundevent_changelist")},
    ]
    return context
