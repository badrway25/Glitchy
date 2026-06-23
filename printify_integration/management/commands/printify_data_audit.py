"""Honest, READ-ONLY audit of Printify data: what the site shows vs what is real,
cached, fallback, demo, or missing.

Never writes to the DB, never creates a SyncLog, never pushes products/orders. Never
prints the API token, Authorization header, or any secret/PII — only field names,
classifications, booleans, and rounded numeric deltas.

Classifications per field:
  real_from_printify  — verified against a live Printify API read (only with --live)
  cached_from_db      — present in DB from a prior sync, not verified live
  fallback            — site computes/serves a non-Printify value (e.g. shipping table,
                        base_cost when variant cost missing, remote mockup URL)
  demo                — hardcoded/local placeholder (e.g. stock 9999, fallback rate table)
  missing             — never synced / empty / sync error
  mismatch            — live Printify value differs from the cached DB value (--live only)

Examples:
  manage.py printify_data_audit                         # all synced products, DB-only
  manage.py printify_data_audit --product-id 6 --json
  manage.py printify_data_audit --product-id 6 --live --compare-site
"""
import argparse
import json

from django.conf import settings
from django.core.management.base import BaseCommand

from store.models import Product


class Command(BaseCommand):
    help = ("Read-only integrity audit of Printify data (real vs cached vs fallback vs "
            "demo vs missing). Never writes, never prints secrets.")

    def add_arguments(self, parser):
        parser.add_argument("--product-id", type=int, default=None)
        parser.add_argument("--printify-product-id", type=str, default=None)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--live", action=argparse.BooleanOptionalAction, default=False,
                            help="Compare against a live Printify read (needs token). Default --no-live.")
        parser.add_argument("--compare-site", action="store_true",
                            help="Also classify what the storefront actually serves (shipping source, buyable variants).")
        parser.add_argument("--safe-output", action="store_true", default=True,
                            help="Redact costs/PII (on by default; token is NEVER printed regardless).")

    def handle(self, *args, **opts):
        qs = Product.objects.all().order_by("id")
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])
        elif opts["printify_product_id"]:
            qs = qs.filter(printify_product_id=opts["printify_product_id"])
        else:
            qs = qs.exclude(printify_product_id__isnull=True).exclude(printify_product_id="")

        live_client = None
        if opts["live"]:
            try:
                from printify_integration.printify_client import get_client
                live_client = get_client()  # token read internally, never returned/printed
                if live_client is None:
                    self._warn(opts, "live requested but no Printify token configured — falling back to DB-only.")
            except Exception:
                live_client = None
                self._warn(opts, "could not init Printify client — DB-only audit.")

        summary = {"products": 0, "real": 0, "cached": 0, "fallback": 0,
                   "demo": 0, "missing": 0, "mismatch": 0}
        detail = []

        bucket = {"real_from_printify": "real", "cached_from_db": "cached",
                  "fallback": "fallback", "demo": "demo", "missing": "missing",
                  "mismatch": "mismatch"}
        for product in qs:
            summary["products"] += 1
            fields = self._audit_product(product, live_client, opts)
            for f in fields:
                b = bucket.get(f["classification"])
                if b:
                    summary[b] += 1
            detail.append({
                "product_id": product.id,
                "printify_product_id_present": bool(product.printify_product_id),
                "name": product.product_name,
                "fields": fields,
            })

        has_mismatch = summary["mismatch"] > 0

        if opts["json"]:
            self.stdout.write(json.dumps({"summary": summary, "detail": detail}, ensure_ascii=False))
        else:
            self._print_text(summary, detail)

        # Useful exit code: non-zero when a live mismatch was detected.
        if has_mismatch:
            raise SystemExit(2)

    # ------------------------------------------------------------------ per product
    def _audit_product(self, p, client, opts):
        fields = []

        def add(field, classification, note=""):
            fields.append({"field": field, "classification": classification, "note": note})

        # Identity / catalogue (cached snapshots)
        add("printify_product_id", "cached_from_db" if p.printify_product_id else "missing")
        add("printify_blueprint_id", "cached_from_db" if p.printify_blueprint_id else "missing")
        add("printify_provider_id", "cached_from_db" if p.printify_provider_id else "missing")
        add("printify_provider_name", "cached_from_db" if p.printify_provider_name else "missing")
        add("printify_sync_status",
            "missing" if p.printify_sync_status in ("not_synced", "error") else "cached_from_db",
            note=p.printify_sync_status)
        add("printify_synced_at", "cached_from_db" if p.printify_synced_at else "missing")

        # Description: real text cached; translations cached; EN fallback if no translation
        add("description", "cached_from_db" if p.description else "missing")

        # Variations
        variations = list(p.variation_set.all())
        buyable = [v for v in variations if getattr(v, "is_buyable", False)]
        add("variations", "cached_from_db" if variations else "missing",
            note=f"{len(buyable)}/{len(variations)} buyable")
        # Per-variant cost: real cost cached, or base_cost fallback, or missing
        costed = [v for v in variations if getattr(v, "production_cost", 0)]
        if costed:
            add("variant_costs", "cached_from_db", note=f"{len(costed)}/{len(variations)} with cost")
        elif p.base_cost:
            add("variant_costs", "fallback", note="using product base_cost")
        else:
            add("variant_costs", "missing")

        # Images: local downloaded (cached) vs remote printify_src only (fallback)
        gallery = list(p.gallery.all()) if hasattr(p, "gallery") else []
        if gallery:
            local = [g for g in gallery if getattr(g, "image", None)]
            add("gallery", "cached_from_db" if local else "fallback",
                note=f"{len(local)}/{len(gallery)} local, rest remote printify_src")
        else:
            add("gallery", "missing")

        # Stock is a hardcoded demo value at sync time (9999)
        add("stock", "demo" if p.stock == 9999 else "cached_from_db", note=str(p.stock))

        # Customer price (cached from enabled-variant price at sync)
        add("price", "cached_from_db" if p.price else "missing")

        # --- live comparison ---
        if client and p.printify_product_id:
            try:
                live = client.get_product(p.printify_product_id)
                if live:
                    # title
                    live_title = (live.get("title") or "").strip()
                    if live_title:
                        if live_title == p.product_name:
                            add("live:title", "real_from_printify")
                        else:
                            add("live:title", "mismatch", note="db≠printify")
                    # visibility
                    live_visible = bool(live.get("visible", True))
                    if live_visible == bool(p.printify_visible):
                        add("live:visible", "real_from_printify")
                    else:
                        add("live:visible", "mismatch")
                    # variant count
                    live_variants = live.get("variants") or []
                    live_enabled = [v for v in live_variants if v.get("is_enabled")]
                    if len(live_enabled) == len(buyable):
                        add("live:enabled_variants", "real_from_printify",
                            note=f"{len(live_enabled)} enabled")
                    else:
                        add("live:enabled_variants", "mismatch",
                            note=f"printify {len(live_enabled)} vs site {len(buyable)}")
            except Exception:
                add("live:read", "missing", note="live read failed — kept cached")

        # --- what the storefront actually serves ---
        if opts["compare_site"]:
            try:
                from shipping.services import quote_for_cart
                from shipping.geo import detect_country
                # synthetic single-item cart for one supported country
                class _Item:
                    def __init__(self, prod):
                        self.product = prod
                        self.quantity = 1
                        self.sub_total = prod.price
                q = quote_for_cart("IT", [_Item(p)], subtotal=p.price)
                src = getattr(q, "source", "fallback")
                cls = "real_from_printify" if src == "printify" else ("demo" if src in ("fallback", "free") else "cached_from_db")
                add("site:shipping_source", cls, note=src)
            except Exception:
                add("site:shipping_source", "fallback", note="quote failed")

        # data quality (derived/cached)
        try:
            add("data_quality_score", "cached_from_db", note=str(p.data_quality_score()))
        except Exception:
            pass

        return fields

    # ------------------------------------------------------------------ output
    def _print_text(self, summary, detail):
        self.stdout.write(self.style.SUCCESS(
            f"[PRINTIFY DATA AUDIT] products={summary['products']} "
            f"real={summary['real']} cached={summary['cached']} fallback={summary['fallback']} "
            f"demo={summary['demo']} missing={summary['missing']} mismatch={summary['mismatch']}"))
        for d in detail:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"#{d['product_id']} {d['name']}"))
            for f in d["fields"]:
                c = f["classification"]
                line = f"  {f['field']}: {c}" + (f"  ({f['note']})" if f["note"] else "")
                if c == "mismatch":
                    self.stdout.write(self.style.ERROR(line))
                elif c in ("missing", "fallback", "demo"):
                    self.stdout.write(self.style.WARNING(line))
                else:
                    self.stdout.write(line)

    def _warn(self, opts, msg):
        if not opts["json"]:
            self.stdout.write(self.style.WARNING(msg))
