"""Seed demo merchandising data from REAL catalog products (idempotent)."""
from django.core.management.base import BaseCommand

from merchandising.models import Collection, Outfit, ProductRelation
from store.models import Product


class Command(BaseCommand):
    help = "Seed collections, outfits and curated relations from real products."

    def handle(self, *args, **options):
        products = list(Product.objects.filter(is_available=True)[:12])
        if len(products) < 3:
            self.stdout.write(self.style.WARNING("Not enough products to seed."))
            return

        # Collections
        collections = [
            ("New Season", "new-season", "Fresh arrivals", "Nuovi arrivi", "Nouveautés",
             "The new season", "La nuova stagione", "La nouvelle saison", True),
            ("Essentials", "essentials", "Everyday staples", "Capi di tutti i giorni",
             "Les essentiels", "Wardrobe essentials", "Essenziali del guardaroba",
             "Les indispensables", True),
            ("Gift Ideas", "gift-ideas", "Perfect presents", "Regali perfetti",
             "Cadeaux parfaits", "Gift ideas", "Idee regalo", "Idées cadeaux", False),
        ]
        for i, (name, slug, st, sit, sfr, ht, hit, hfr, feat) in enumerate(collections):
            c, _ = Collection.objects.update_or_create(slug=slug, defaults=dict(
                name=name, subtitle=st, subtitle_it=sit, subtitle_fr=sfr,
                hero_title=ht, hero_title_it=hit, hero_title_fr=hfr,
                is_active=True, featured=feat, order=i))
            c.products.set(products[i * 3:i * 3 + 6] or products[:6])

        # Outfit (complete the look) anchored to the first product
        anchor = products[0]
        o, _ = Outfit.objects.update_or_create(title="Weekend Off-Duty", defaults=dict(
            title_it="Look del weekend", title_fr="Look du week-end",
            description="Relaxed pieces that work together.",
            description_it="Capi rilassati che stanno bene insieme.",
            description_fr="Des pièces décontractées qui vont bien ensemble.",
            anchor_product=anchor, is_active=True, featured=True, order=0))
        o.products.set(products[:4])

        # Curated relations on the anchor product
        for j, p in enumerate(products[1:5]):
            rtype = ProductRelation.COMPLETE_LOOK if j < 2 else ProductRelation.BEST_MATCH
            ProductRelation.objects.update_or_create(
                from_product=anchor, to_product=p, relation_type=rtype,
                defaults=dict(order=j, is_active=True))

        self.stdout.write(self.style.SUCCESS(
            f"Merchandising seeded: {Collection.objects.count()} collections, "
            f"{Outfit.objects.count()} outfits, {ProductRelation.objects.count()} relations."))
