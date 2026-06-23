"""Remove the technical 'Printify' category: re-home its products to a commercial
category, then delete the empty technical bucket.

SAFE & idempotent:
- Dry-run by default; --apply makes changes.
- Products are ALWAYS reassigned BEFORE the category is deleted (Product.category is
  on_delete=CASCADE, so deleting first would destroy products — this command never does that).
- If no 'Printify' category exists, it is a clean no-op.
- No secrets / no PII in output.

Examples:
  manage.py cleanup_printify_category                         # dry-run
  manage.py cleanup_printify_category --apply
  manage.py cleanup_printify_category --apply --fallback-category t-shirt
  manage.py cleanup_printify_category --json
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand

from category.models import Category
from store.models import Product


class Command(BaseCommand):
    help = ("Re-home products out of the technical 'Printify' category and delete it. "
            "Dry-run by default.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually reassign products and delete the category (default: dry-run).")
        parser.add_argument("--fallback-category", type=str, default=None,
                            help="Slug of the commercial category to move products into "
                                 "(default: PRINTIFY_DEFAULT_CATEGORY_SLUG).")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        dry_run = not opts["apply"]

        # Find any technical 'Printify' bucket (by slug or name, case-insensitive).
        tech = list(Category.objects.filter(slug__iexact="printify")) \
            or list(Category.objects.filter(category_name__iexact="printify"))

        # Resolve the commercial fallback target.
        fb_slug = (opts["fallback_category"]
                   or getattr(settings, "PRINTIFY_DEFAULT_CATEGORY_SLUG", "t-shirt") or "t-shirt")
        target = Category.objects.filter(slug=fb_slug).first() \
            or Category.objects.filter(is_public=True).exclude(slug__iexact="printify").order_by("id").first()

        result = {"found": len(tech), "fallback": fb_slug,
                  "target_resolved": bool(target), "reassigned": 0, "deleted": 0,
                  "applied": opts["apply"]}

        if not tech:
            return self._emit(opts, result, note="No 'Printify' category — nothing to do.")
        if not target:
            return self._emit(opts, result, note="No commercial fallback category available — aborting.",
                              level="warning")

        for cat in tech:
            n = Product.objects.filter(category=cat).count()
            result["reassigned"] += n
            if opts["apply"]:
                Product.objects.filter(category=cat).update(category=target)
                cat.delete()
                result["deleted"] += 1

        note = (f"[{'APPLIED' if opts['apply'] else 'DRY-RUN'}] "
                f"category 'Printify' x{result['found']} -> moved {result['reassigned']} "
                f"product(s) to '{target.category_name}' ({fb_slug}); "
                f"deleted {result['deleted']} categor(y/ies).")
        if dry_run:
            note += " Re-run with --apply to perform."
        return self._emit(opts, result, note=note)

    def _emit(self, opts, result, note="", level="success"):
        if opts["json"]:
            self.stdout.write(json.dumps({"ok": True, "note": note, **result}))
            return
        style = {"success": self.style.SUCCESS, "warning": self.style.WARNING}.get(level, self.style.NOTICE)
        self.stdout.write(style(note))
