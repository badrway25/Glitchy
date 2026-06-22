"""Import & persist Printify shipping profiles and print-area coverage.

Read-only against Printify (get_shipping_info / product payload), writes only to our own
tables. Never creates orders, never pushes. No secrets, no PII.
"""
from django.utils import timezone

from .models import PrintifyPrintArea, PrintifyShippingProfile


def _cents(v):
    try:
        return round(float(v) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def import_shipping_profiles(blueprint_id, provider_id, *, client=None, dry_run=False,
                             blueprint_title="", provider_name="", countries=None):
    """Upsert shipping rows for one (blueprint, provider). Returns a summary dict.
    Idempotent: re-running updates the same rows, never duplicates."""
    from .printify_client import PrintifyClient, PrintifyError
    client = client or PrintifyClient()
    summary = {"blueprint_id": blueprint_id, "provider_id": provider_id,
               "created": 0, "updated": 0, "countries": [], "error": None}
    try:
        info = client.get_shipping_info(blueprint_id, provider_id)
    except PrintifyError as e:
        summary["error"] = str(e)[:120]
        return summary
    except Exception as e:
        summary["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        return summary

    if not isinstance(info, dict) or not info.get("profiles"):
        summary["error"] = "no_profiles"
        return summary

    handling = (info.get("handling_time") or {}).get("value", 3)
    try:
        handling = int(handling)
    except (TypeError, ValueError):
        handling = 3
    min_days, max_days = handling + 3, handling + 8

    from .shipping import _pick_profile
    # Resolve one row PER requested country, picking its country-specific profile
    # (or the REST_OF_THE_WORLD fallback) — mirrors the live shipping quote logic.
    if countries:
        wanted = [c.upper() for c in countries]
    else:
        explicit = {str(c).upper() for prof in info["profiles"]
                    for c in (prof.get("countries") or []) if str(c).upper() != "REST_OF_THE_WORLD"}
        wanted = sorted(explicit | {"IT", "FR", "BE", "DE", "ES", "MA"})

    for cc in wanted:
        prof = _pick_profile(info["profiles"], cc)
        if not prof:
            continue
        first = prof.get("first_item") or {}
        add = prof.get("additional_items") or {}
        currency = first.get("currency") or "USD"
        summary["countries"].append(cc)
        if dry_run:
            continue
        obj, created = PrintifyShippingProfile.objects.update_or_create(
            blueprint_id=blueprint_id, print_provider_id=provider_id, country_code=cc,
            defaults=dict(
                blueprint_title=blueprint_title[:160], print_provider_name=provider_name[:120],
                first_item_cost=_cents(first.get("cost")),
                additional_item_cost=_cents(add.get("cost")),
                currency=currency, handling_days=handling,
                min_delivery_days=min_days, max_delivery_days=max_days,
                source="printify", last_checked_at=timezone.now()),
        )
        summary["created" if created else "updated"] += 1
    return summary


def import_print_areas(product, payload):
    """Upsert PrintifyPrintArea rows from a product payload's print_areas. Idempotent."""
    areas = payload.get("print_areas") or []
    created = updated = 0
    seen = set()
    for area in areas:
        variant_count = len(area.get("variant_ids") or [])
        bp = payload.get("blueprint_id")
        pv = payload.get("print_provider_id")
        for ph in area.get("placeholders") or []:
            position = (ph.get("position") or "").strip()[:40]
            if not position or position in seen:
                continue
            seen.add(position)
            has_file = bool(ph.get("images"))
            obj, was_created = PrintifyPrintArea.objects.update_or_create(
                product=product, position=position,
                defaults=dict(blueprint_id=bp, print_provider_id=pv,
                              placeholder_count=len(area.get("placeholders") or []),
                              has_print_file=has_file, variant_count=variant_count,
                              last_synced_at=timezone.now()),
            )
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
    return {"created": created, "updated": updated, "positions": sorted(seen)}


def sync_all_shipping_profiles(*, dry_run=True, countries=None, client=None,
                               product_id=None, limit=None):
    """Iterate distinct (blueprint, provider) across local synced products and import.
    dry_run=True by default (no writes)."""
    from store.models import Product
    qs = Product.objects.exclude(printify_blueprint_id__isnull=True)\
        .exclude(printify_provider_id__isnull=True)
    if product_id:
        qs = qs.filter(id=product_id)
    if limit:
        qs = qs[:limit]
    seen, results = set(), []
    for p in qs:
        key = (p.printify_blueprint_id, p.printify_provider_id)
        if key in seen:
            continue
        seen.add(key)
        results.append(import_shipping_profiles(
            p.printify_blueprint_id, p.printify_provider_id, client=client, dry_run=dry_run,
            blueprint_title=p.printify_blueprint_title, provider_name=p.printify_provider_name,
            countries=countries))
    total = {"pairs": len(results),
             "created": sum(r["created"] for r in results),
             "updated": sum(r["updated"] for r in results),
             "countries": sorted({c for r in results for c in r["countries"]}),
             "errors": [r for r in results if r["error"]]}
    return total, results
