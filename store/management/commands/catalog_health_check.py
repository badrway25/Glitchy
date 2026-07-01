"""Catalog health check — flags catalog gaps for the admin dashboard / ops.

Safe output only: counts + product slugs (slugs are public, not PII). Never a token, price
secret, customer name/email, or address. Use --json for machine-readable output.

    python manage.py catalog_health_check --json --safe-output
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from store.models import Product


def collect(sample=8):
    qs = Product.objects.all()
    cutoff = timezone.now() - timezone.timedelta(
        minutes=getattr(settings, "PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360))

    checks = {}

    def add(key, q):
        rows = list(qs.filter(q) if isinstance(q, Q) else q)
        checks[key] = {"count": len(rows), "sample": [p.slug for p in rows[:sample]]}

    add("missing_image", qs.annotate(_g=Count("gallery")).filter(_g=0).filter(
        Q(images="") | Q(images__isnull=True)))
    add("missing_price", Q(price__isnull=True) | Q(price__lte=0))
    add("missing_category", Q(category__isnull=True))
    add("missing_description", Q(description="") | Q(description__isnull=True))
    add("empty_gallery", qs.annotate(_g=Count("gallery")).filter(_g=0))
    add("no_variants", qs.annotate(_v=Count("variation")).filter(_v=0))
    add("stale_printify_sync", qs.filter(printify_product_id__isnull=False,
                                         printify_synced_at__lt=cutoff))
    add("printify_sync_error", Q(printify_sync_status="error"))
    add("active_but_out_of_stock", Q(is_available=True) & (Q(stock__lte=0)))

    # duplicate slugs (should be impossible with unique=True, but surface anyway)
    dup = (qs.values("slug").annotate(n=Count("id")).filter(n__gt=1))
    checks["duplicate_slugs"] = {"count": dup.count(), "sample": [d["slug"] for d in dup[:sample]]}

    total = qs.count()
    # score reflects HARD content gaps only; soft/informational checks (empty gallery,
    # no variants, stale sync) are surfaced but don't tank the score.
    hard = ("missing_image", "missing_price", "missing_category", "missing_description",
            "printify_sync_error", "duplicate_slugs", "active_but_out_of_stock")
    hard_issues = sum(checks[k]["count"] for k in hard if k in checks)
    score = 100 if not total else max(0, round(100 - (hard_issues / max(total, 1)) * 100))
    return {"total_products": total, "health_score": score, "checks": checks}


class Command(BaseCommand):
    help = "Report catalog data-quality gaps (safe output: counts + slugs only)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
        parser.add_argument("--safe-output", action="store_true",
                            help="No-op flag documenting that output carries no PII/secrets.")

    def handle(self, *args, **opts):
        report = collect()
        if opts.get("json"):
            self.stdout.write(json.dumps(report, indent=2))
            return
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Catalog health: %(s)s%% (%(t)d products)" % {
                "s": report["health_score"], "t": report["total_products"]}))
        for key, data in report["checks"].items():
            n = data["count"]
            line = "  %-24s %d" % (key, n)
            self.stdout.write(self.style.ERROR(line) if n else self.style.SUCCESS(line))
