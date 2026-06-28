"""Audit pre-order shipping estimates per country (cost + delivery + source).

    python manage.py printify_shipping_estimate_audit                       # IT/FR/BE, configured mode
    python manage.py printify_shipping_estimate_audit --country IT --country US
    python manage.py printify_shipping_estimate_audit --product-id 6 --live --json
    python manage.py printify_shipping_estimate_audit --no-live             # force fallback

Output is SAFE: country codes, costs, delivery ranges, source and missing-data
flags only. It never prints a token, address, name, email or raw API payload,
and it never creates an order. `--live` temporarily reads the live Printify
order-shipping endpoint (read-only) for THIS process only.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand

# Plausible sample postal codes per country (used only to exercise the live
# endpoint; never a real customer address).
SAMPLE_ZIP = {
    "IT": "20100", "FR": "75001", "BE": "1000", "DE": "10115", "ES": "28001",
    "NL": "1011", "AT": "1010", "PT": "1000", "IE": "D01", "CH": "8001",
    "GB": "SW1A 1AA", "US": "10001", "CA": "M5V", "AU": "2000",
}


class _StubCartItem:
    """Minimal cart line for the estimator (real Product, no DB CartItem)."""
    class _Vars:
        def all(self):
            return []

    def __init__(self, product, quantity=1):
        self.product = product
        self.quantity = quantity
        self.variations = self._Vars()
        self.printify_variant_id = None


class Command(BaseCommand):
    help = "Audit pre-order shipping estimates per country (safe output, no order push)."

    def add_arguments(self, parser):
        parser.add_argument("--country", action="append", default=None,
                            help="Country code(s) to audit; repeatable.")
        parser.add_argument("--product-id", type=int, default=None)
        parser.add_argument("--variant-id", type=int, default=None,
                            help="Force a Printify variant id on the sample line.")
        parser.add_argument("--limit", type=int, default=5,
                            help="Max products to include when no --product-id is given.")
        parser.add_argument("--live", action="store_true", help="Read live Printify rates.")
        parser.add_argument("--no-live", action="store_true", help="Force fallback (no API).")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--safe-output", action="store_true",
                            help="Affirm safe output (no PII/token). Always enforced.")

    def handle(self, *args, **opts):
        from printify_integration.shipping_estimator import estimate_for_cart
        from store.models import Product

        # Live mode toggle (process-local; never writes settings to disk).
        if opts["live"] and opts["no_live"]:
            self.stderr.write(self.style.ERROR("Use either --live or --no-live, not both."))
            return
        if opts["live"]:
            settings.SHIPPING_USE_PRINTIFY = True
        elif opts["no_live"]:
            settings.SHIPPING_USE_PRINTIFY = False
        mode = "live" if getattr(settings, "SHIPPING_USE_PRINTIFY", False) else "fallback"

        # Build a representative cart from synced products.
        qs = Product.objects.filter(is_available=True)
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])
        else:
            qs = qs.exclude(printify_blueprint_id__isnull=True)[:opts["limit"]]
        products = list(qs)
        if not products:
            products = list(Product.objects.filter(is_available=True)[:1])
        if not products:
            self.stderr.write(self.style.ERROR("No products available to audit."))
            return
        cart = [_StubCartItem(p, quantity=1) for p in products]
        if opts["variant_id"]:
            cart[0].printify_variant_id = opts["variant_id"]

        countries = [c.upper() for c in (opts["country"] or ["IT", "FR", "BE"])]

        rows = []
        for cc in countries:
            r = estimate_for_cart(cart, cc, postal_code=SAMPLE_ZIP.get(cc, ""),
                                  use_cache=False)
            rows.append({
                "country": cc,
                "available": r.available,
                "source": r.source,
                "method": r.selected_method,
                "cost": r.shipping_cost,
                "currency": r.currency,
                "production_days": [r.production_days_min, r.production_days_max],
                "transit_days": [r.transit_days_min, r.transit_days_max],
                "delivery_days": [r.delivery_days_min, r.delivery_days_max],
                "options": [o.method for o in r.options],
                "missing": r.errors_safe,
            })

        summary = {
            "mode": mode,
            "products_in_cart": len(products),
            "countries": len(rows),
            "live_count": sum(1 for r in rows if r["source"] == "live_printify"),
            "cached_count": sum(1 for r in rows if r["source"] == "cached_profile"),
            "fallback_count": sum(1 for r in rows if r["source"] == "local_fallback"),
            "unavailable_count": sum(1 for r in rows if not r["available"]),
        }

        if opts["json"]:
            self.stdout.write(json.dumps({"summary": summary, "rows": rows}, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(
            f"[mode={mode}] products={len(products)} countries={len(rows)} "
            f"live={summary['live_count']} cached={summary['cached_count']} "
            f"fallback={summary['fallback_count']} unavailable={summary['unavailable_count']}"))
        for r in rows:
            if not r["available"]:
                self.stdout.write(self.style.WARNING(
                    f"  {r['country']}: UNAVAILABLE ({','.join(r['missing']) or 'no route'})"))
                continue
            sym = r["currency"]
            cost = "Free" if not r["cost"] else f"{sym} {r['cost']:.2f}"
            d = r["delivery_days"]
            self.stdout.write(
                f"  {r['country']}: {r['source']:<14} {r['method']:<9} {cost:<10} "
                f"delivery {d[0]}-{d[1]}d (prod {r['production_days'][0]}-{r['production_days'][1]} "
                f"+ transit {r['transit_days'][0]}-{r['transit_days'][1]}) "
                f"opts={','.join(r['options'])}")
        if mode == "fallback":
            self.stdout.write(self.style.NOTICE(
                "Fallback mode: costs/times are estimates. Run with --live (and "
                "SHIPPING_USE_PRINTIFY) to read live Printify rates."))
