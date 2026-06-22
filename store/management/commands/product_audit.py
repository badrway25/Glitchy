"""Product completeness / data-quality audit (admin-only, no PII, no secrets).

    python manage.py product_audit            # summary + low-quality list
    python manage.py product_audit --json     # machine-readable

Reports the same categories as the admin completeness dashboard: missing composition,
gallery, costs, provider, sync, FAQ, etc. Never prints customer data or secrets.
"""
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Audit product data completeness (no PII / secrets)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--threshold", type=int, default=80)

    def handle(self, *args, **opts):
        from store.models import Product, Variation
        buckets = {
            "no_composition": [], "no_gallery": [], "no_costs": [], "no_provider": [],
            "not_synced": [], "no_faq": [], "low_quality": [], "not_visible": [],
        }
        scores = []
        for p in Product.objects.all():
            dq = p.data_quality()
            scores.append(dq["score"])
            miss = set(dq["missing"])
            if "composition" in miss:
                buckets["no_composition"].append(p.product_name)
            if "gallery_multi" in miss:
                buckets["no_gallery"].append(p.product_name)
            if "variant_costs" in miss:
                buckets["no_costs"].append(p.product_name)
            if "blueprint_provider" in miss:
                buckets["no_provider"].append(p.product_name)
            if "synced" in miss:
                buckets["not_synced"].append(p.product_name)
            if "faq" in miss:
                buckets["no_faq"].append(p.product_name)
            if dq["score"] < opts["threshold"]:
                buckets["low_quality"].append(f"{p.product_name} ({dq['score']}%)")
            if not p.printify_visible:
                buckets["not_visible"].append(p.product_name)

        avg = round(sum(scores) / len(scores)) if scores else 0
        summary = {"products": len(scores), "avg_quality": avg,
                   **{k: len(v) for k, v in buckets.items()}}

        if opts["json"]:
            self.stdout.write(json.dumps({"summary": summary, "detail": buckets}, indent=2))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nProducts: {summary['products']} · Avg data quality: {avg}%\n"))
        for k, items in buckets.items():
            if items:
                style = self.style.WARNING if k != "low_quality" else self.style.ERROR
                self.stdout.write(style(f"  {k:16} {len(items):3}  ") +
                                  ", ".join(i[:30] for i in items[:6]))
        if not any(buckets.values()):
            self.stdout.write(self.style.SUCCESS("  All products complete."))
