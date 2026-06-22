"""Sanitize descriptions already stored with raw HTML (dry-run by default).

    python manage.py clean_product_descriptions            # dry-run: report only
    python manage.py clean_product_descriptions --apply     # write cleaned text
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Strip raw HTML from stored product descriptions (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the cleaned descriptions (default is a dry-run).")
        parser.add_argument("--product-id", type=int, default=None)

    def handle(self, *args, **opts):
        from store.models import Product
        from printify_integration.text import clean_printify_description, looks_like_html

        qs = Product.objects.all()
        if opts["product_id"]:
            qs = qs.filter(id=opts["product_id"])

        dirty = examined = changed = 0
        for p in qs:
            examined += 1
            if not looks_like_html(p.description):
                continue
            dirty += 1
            cleaned = clean_printify_description(p.description)
            if cleaned != (p.description or ""):
                changed += 1
                if opts["apply"]:
                    p.description = cleaned[:2000]
                    p.save(update_fields=["description"])

        mode = "APPLIED" if opts["apply"] else "DRY-RUN (no changes written)"
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] examined={examined} had_html={dirty} cleaned={changed}"))
        if not opts["apply"] and dirty:
            self.stdout.write(self.style.NOTICE("Re-run with --apply to write the cleaned text."))
