"""Enrich the catalogue with realistic, HONEST product data for staging review.

Idempotent + dev/staging only: it fills empty composition / fit / care fields, sets a
compare_at_price on a couple of items (so the Sale filter/badge fire), and ensures every
product has colour + size variations (so those filters fire) — WITHOUT overwriting any
real data and WITHOUT inventing unverifiable claims (no 'sustainable', no fake origin).
It never creates fake imagery: products keep whatever gallery they already have.

    python manage.py seed_staging_catalog          # enrich
    python manage.py seed_staging_catalog --reset   # also re-apply to already-filled fields

Do NOT run on production without confirming the copy matches the real garments.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from store.models import Product, Variation

# Honest, print-on-demand-appropriate copy (no false sustainability/origin claims).
COMPOSITION = [
    "100% combed ring-spun cotton, mid-weight (180 gsm).",
    "Soft-touch cotton blend (85% cotton, 15% polyester).",
    "Heavyweight 240 gsm cotton for structure and durability.",
    "Premium cotton jersey with a smooth printable surface.",
]
FIT = [
    "Regular fit. If you're between sizes, size up for a relaxed look.",
    "Relaxed, unisex fit with dropped shoulders.",
    "True to size with a classic straight cut.",
]
CARE = [
    "Machine wash cold, inside out. Do not tumble dry. Do not iron the print.",
    "Wash at 30°C with similar colours. Hang to dry to protect the print.",
]
COLORS = ["Black", "White", "Blu", "Green"]
SIZES = ["S", "M", "L", "XL"]


class Command(BaseCommand):
    help = "Enrich the catalogue with realistic composition/fit/care, sale prices and variations."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Re-apply copy even to already-filled fields.")

    def handle(self, *args, **options):
        reset = options["reset"]
        products = list(Product.objects.all().order_by("id"))
        if not products:
            self.stdout.write(self.style.WARNING("No products to enrich."))
            return

        enriched = sale = var_added = 0
        for i, p in enumerate(products):
            fields = []
            if reset or not p.composition:
                p.composition = COMPOSITION[i % len(COMPOSITION)]; fields.append("composition")
            if reset or not p.fit_notes:
                p.fit_notes = FIT[i % len(FIT)]; fields.append("fit_notes")
            if reset or not p.care_instructions:
                p.care_instructions = CARE[i % len(CARE)]; fields.append("care_instructions")
            # Put ~1 in 3 on sale (compare_at_price strictly above price).
            if (reset or not p.compare_at_price) and i % 3 == 0 and p.price:
                p.compare_at_price = int(round(p.price * Decimal("1.3")))
                fields.append("compare_at_price"); sale += 1
            # Mark the first two as bestseller / featured for merchandising.
            if i == 0 and not p.is_bestseller:
                p.is_bestseller = True; fields.append("is_bestseller")
            if i == 1 and not p.is_featured:
                p.is_featured = True; fields.append("is_featured")
            if fields:
                p.save(update_fields=fields + ["modified_date"])
                enriched += 1

            # Ensure colour + size variations exist so those filters fire.
            for c in COLORS[: 3 if i % 2 == 0 else 2]:
                _, created = Variation.objects.get_or_create(
                    product=p, variation_category="color", variation_value=c,
                    defaults={"is_active": True})
                var_added += int(created)
            for s in SIZES:
                _, created = Variation.objects.get_or_create(
                    product=p, variation_category="size", variation_value=s,
                    defaults={"is_active": True})
                var_added += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"Catalogue enriched: {enriched} products updated, {sale} on sale, "
            f"{var_added} variations added. (Galleries untouched — add real images via admin.)"))
