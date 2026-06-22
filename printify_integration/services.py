"""
Printify synchronisation services.

Reusable functions (called by management commands AND admin actions) that sync
products, capture production costs, refresh order statuses, and record a SyncLog
for observability. Robust against partial failures: one bad product never aborts
the whole run.
"""
from __future__ import annotations

import logging
import os

import requests
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from category.models import Category
from store.models import Product, ProductImage, Variation
from .models import SyncLog
from .printify_client import PrintifyError, get_client

logger = logging.getLogger("printify")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _unique_slug(name: str) -> str:
    base = slugify(name)[:180] or "product"
    slug, i = base, 2
    while Product.objects.filter(slug=slug).exists():
        suffix = f"-{i}"
        slug = base[:200 - len(suffix)] + suffix
        i += 1
    return slug


def _cents_to_units(value) -> float:
    try:
        return round(int(value) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _download_image(url: str, timeout: int = 30):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        filename = os.path.basename(url.split("?")[0]) or "image.jpg"
        return filename, r.content
    except Exception:
        return None


def _category_for(p: dict, fallback: Category, settings_map: dict) -> Category:
    bp = p.get("blueprint_id")
    try:
        bp_int = int(bp) if bp is not None else None
    except (TypeError, ValueError):
        bp_int = None
    cat_slug = (settings_map or {}).get(bp_int)
    if not cat_slug:
        return fallback
    cat = Category.objects.filter(slug=cat_slug).first()
    if cat:
        return cat
    name = cat_slug.replace("-", " ").title()
    cat, _ = Category.objects.get_or_create(
        slug=cat_slug,
        defaults={"category_name": name, "description": "Auto-created from Printify blueprint mapping"},
    )
    return cat


def _enabled_variant_info(p: dict):
    """Return (retail_price_units, production_cost_units) from enabled variants."""
    variants = p.get("variants") or []
    price = cost = 0.0
    enabled = [v for v in variants if v.get("is_enabled")] or variants
    if enabled:
        price = _cents_to_units(enabled[0].get("price"))
        # min production cost across enabled variants
        costs = [_cents_to_units(v.get("cost")) for v in enabled if v.get("cost")]
        cost = min(costs) if costs else 0.0
    return price, cost


def _sync_variations(product: Product, p: dict):
    """Map Printify options (color/size) to store.Variation, capturing cost."""
    options = p.get("options") or []
    option_value_map = {}
    for opt in options:
        opt_type = (opt.get("type") or "").lower()
        for val in opt.get("values") or []:
            option_value_map[val.get("id")] = (opt_type, (val.get("title") or "").strip())

    _, prod_cost = _enabled_variant_info(p)
    created = updated = 0
    for v in p.get("variants") or []:
        if not v.get("is_enabled"):
            continue
        variant_id = str(v.get("id") or "")
        if not variant_id:
            continue
        v_cost = _cents_to_units(v.get("cost")) or prod_cost
        for oid in v.get("options") or []:
            mapped = option_value_map.get(oid)
            if not mapped:
                continue
            opt_type, opt_title = mapped
            if opt_type not in ("color", "size") or not opt_title:
                continue
            existing = Variation.objects.filter(
                product=product, variation_category=opt_type,
                variation_value__iexact=opt_title,
            ).first()
            if existing is None:
                Variation.objects.create(
                    product=product, variation_category=opt_type, variation_value=opt_title,
                    is_active=True, printify_variant_id=variant_id, production_cost=v_cost,
                )
                created += 1
            else:
                changed = False
                if not existing.printify_variant_id:
                    existing.printify_variant_id = variant_id
                    changed = True
                if v_cost and existing.production_cost != v_cost:
                    existing.production_cost = v_cost
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True
                if changed:
                    existing.save()
                    updated += 1
    return created, updated


def _sync_images(product: Product, p: dict, refresh=False):
    images = p.get("images") or []
    if not images:
        return
    if refresh:
        for pi in ProductImage.objects.filter(product=product):
            try:
                if pi.image:
                    pi.image.delete(save=False)
            except Exception:
                pass
        ProductImage.objects.filter(product=product).delete()
    if ProductImage.objects.filter(product=product).exists():
        return
    default_src = None
    for img in images:
        url = img.get("src")
        if not url:
            continue
        is_def = bool(img.get("is_default"))
        if is_def and not default_src:
            default_src = url
        dl = _download_image(url)
        if not dl:
            continue
        filename, content = dl
        pi = ProductImage(product=product, is_default=is_def)
        pi.image.save(filename, ContentFile(content), save=True)
    if not product.images and default_src:
        dl = _download_image(default_src)
        if dl:
            filename, content = dl
            product.images.save(filename, ContentFile(content), save=True)


def _upsert_product(p: dict, fallback_category, settings_map, overwrite_category, *, refresh_images=False):
    """Create or update a single Product from a Printify product dict."""
    from django.conf import settings as dj_settings

    p_id = str(p.get("id") or "")
    title = (p.get("title") or "").strip()
    desc = (p.get("description") or "").strip()
    if not p_id or not title:
        return None, False

    price, cost = _enabled_variant_info(p)
    category = _category_for(p, fallback_category, settings_map)
    is_draft = not bool(p.get("visible", True))

    obj = Product.objects.filter(printify_product_id=p_id).first()
    is_new = obj is None
    if is_new:
        obj = Product(
            product_name=title, slug=_unique_slug(title), description=desc[:2000],
            price=round(price) or 0, base_cost=cost, stock=9999, is_available=not is_draft,
            category=category, printify_product_id=p_id,
        )
    else:
        obj.product_name = title
        obj.description = desc[:2000]
        if price:
            obj.price = round(price)
        if cost:
            obj.base_cost = cost
        obj.is_available = not is_draft
        obj.stock = max(obj.stock, 9999)
        if overwrite_category or not obj.category_id:
            obj.category = category

    obj.printify_blueprint_id = p.get("blueprint_id") or obj.printify_blueprint_id
    obj.printify_provider_id = p.get("print_provider_id") or obj.printify_provider_id
    obj.printify_sync_status = Product.SYNC_DRAFT if is_draft else (
        Product.SYNC_SYNCED if is_new else Product.SYNC_UPDATED)
    obj.printify_synced_at = timezone.now()
    obj.printify_sync_error = ""
    obj.save()

    _sync_images(obj, p, refresh=refresh_images)
    _sync_variations(obj, p)
    return obj, is_new


# --------------------------------------------------------------------------- #
# Public services
# --------------------------------------------------------------------------- #
def sync_products(*, limit=50, max_pages=20, fallback_category_name="Printify",
                  refresh_images=False, client=None) -> SyncLog:
    from django.conf import settings as dj_settings

    log = SyncLog.objects.create(kind=SyncLog.KIND_PRODUCTS)
    client = client or get_client()
    settings_map = getattr(dj_settings, "PRINTIFY_BLUEPRINT_CATEGORY_MAP", {}) or {}
    overwrite_category = bool(getattr(dj_settings, "PRINTIFY_SYNC_OVERWRITE_CATEGORY", False))

    fallback_category, _ = Category.objects.get_or_create(
        category_name=fallback_category_name,
        defaults={"slug": slugify(fallback_category_name), "description": "Imported from Printify"},
    )

    created = updated = errors = 0
    try:
        for page in range(1, max_pages + 1):
            payload = client.list_products(limit=limit, page=page)
            data = payload.get("data") or []
            if not data:
                break
            for p in data:
                try:
                    obj, is_new = _upsert_product(p, fallback_category, settings_map,
                                                  overwrite_category, refresh_images=refresh_images)
                    if obj is None:
                        continue
                    created += int(is_new)
                    updated += int(not is_new)
                except Exception as exc:
                    errors += 1
                    logger.warning("Product sync error for %s: %s", p.get("id"), exc)
        log.status = SyncLog.STATUS_OK if errors == 0 else SyncLog.STATUS_PARTIAL
        log.message = f"Synced page-by-page. created={created} updated={updated} errors={errors}"
    except PrintifyError as exc:
        log.status = SyncLog.STATUS_ERROR
        log.message = f"Printify API error: {exc}"
    finally:
        log.created_count = created
        log.updated_count = updated
        log.error_count = errors
        log.finished_at = timezone.now()
        log.save()
    return log


def resync_product(product: Product, client=None) -> SyncLog:
    """Resync a single product from Printify (used by admin action)."""
    from django.conf import settings as dj_settings

    log = SyncLog.objects.create(kind=SyncLog.KIND_SINGLE)
    client = client or get_client()
    settings_map = getattr(dj_settings, "PRINTIFY_BLUEPRINT_CATEGORY_MAP", {}) or {}
    fallback_category, _ = Category.objects.get_or_create(
        category_name="Printify",
        defaults={"slug": "printify", "description": "Imported from Printify"},
    )
    try:
        if not product.printify_product_id:
            raise PrintifyError("Product has no printify_product_id")
        p = client.get_product(product.printify_product_id)
        _upsert_product(p, fallback_category, settings_map, False, refresh_images=False)
        log.status = SyncLog.STATUS_OK
        log.updated_count = 1
        log.message = f"Resynced {product.product_name}"
    except Exception as exc:
        log.status = SyncLog.STATUS_ERROR
        log.error_count = 1
        log.message = str(exc)
        product.printify_sync_status = Product.SYNC_ERROR
        product.printify_sync_error = str(exc)[:1000]
        product.save(update_fields=["printify_sync_status", "printify_sync_error"])
    finally:
        log.finished_at = timezone.now()
        log.save()
    return log


def pull_order_statuses(limit=20, client=None) -> SyncLog:
    """Refresh printify_status + tracking for orders that were sent to Printify."""
    from orders.models import Order

    log = SyncLog.objects.create(kind=SyncLog.KIND_ORDERS)
    client = client or get_client()
    updated = errors = 0
    orders = Order.objects.exclude(printify_order_id__isnull=True).exclude(
        printify_order_id="").order_by("-created_at")[:limit]
    try:
        for order in orders:
            try:
                old_status = order.printify_status or ""
                had_tracking = bool(order.tracking_number)
                data = client.get_order(order.printify_order_id)
                fields = []
                status = data.get("status")
                if status and status != order.printify_status:
                    order.printify_status = status[:32]
                    fields.append("printify_status")
                shipments = data.get("shipments") or []
                if shipments:
                    sh = shipments[0]
                    if sh.get("tracking_number"):
                        order.tracking_number = str(sh["tracking_number"])[:128]
                        fields.append("tracking_number")
                    if sh.get("tracking_url"):
                        order.tracking_url = str(sh["tracking_url"])[:200]
                        fields.append("tracking_url")
                    if sh.get("carrier"):
                        order.carrier = str(sh["carrier"])[:64]
                        fields.append("carrier")
                if fields:
                    order.save(update_fields=fields + ["updated_at"])
                    updated += 1
                    # Fire fulfillment emails on a real transition (best-effort, never breaks sync).
                    from orders.fulfillment_notify import notify_fulfillment_transition
                    notify_fulfillment_transition(order, old_status, order.printify_status or "",
                                                  tracking_added=(not had_tracking and bool(order.tracking_number)))
            except Exception as exc:
                errors += 1
                logger.warning("Order pull error %s: %s", order.order_number, exc)
        log.status = SyncLog.STATUS_OK if errors == 0 else SyncLog.STATUS_PARTIAL
        log.updated_count = updated
        log.error_count = errors
        log.message = f"Pulled statuses. updated={updated} errors={errors}"
    except PrintifyError as exc:
        log.status = SyncLog.STATUS_ERROR
        log.message = str(exc)
    finally:
        log.finished_at = timezone.now()
        log.save()
    return log
