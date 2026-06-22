"""Enrich EXISTING real collections with mood/season/editorial metadata (idempotent).

Only fills empty fields on collections that already exist — never creates fake collections
or products. Safe to re-run. Maps by slug; unknown slugs are skipped.

    python manage.py seed_collection_editorial            # dry-run
    python manage.py seed_collection_editorial --apply
"""
from django.core.management.base import BaseCommand

# Editorial metadata keyed by slug. EN/IT/FR intros. Coherent with the real collections.
DATA = {
    "new-season": {
        "mood": "everyday", "season": "new_season",
        "subtitle": "Fresh arrivals", "seo_title": "New Season — fresh arrivals",
        "meta_description": "The latest made-on-demand pieces, fresh off the press.",
        "editorial_intro": "Our newest drop — versatile pieces designed to slot straight into your everyday rotation, printed only when you order.",
        "editorial_intro_it": "Il nostro drop più recente — capi versatili pensati per entrare subito nella tua routine quotidiana, stampati solo quando ordini.",
        "editorial_intro_fr": "Notre dernière sélection — des pièces polyvalentes conçues pour s'intégrer à votre quotidien, imprimées uniquement à la commande.",
    },
    "essentials": {
        "mood": "minimal", "season": "essentials",
        "subtitle": "Everyday staples", "seo_title": "Essentials — everyday staples",
        "meta_description": "Clean, minimal staples built to be worn on repeat.",
        "editorial_intro": "The quiet core of the wardrobe — clean, minimal staples in soft, durable fabrics, made to be worn on repeat.",
        "editorial_intro_it": "Il cuore essenziale del guardaroba — capi puliti e minimal in tessuti morbidi e resistenti, fatti per essere indossati di continuo.",
        "editorial_intro_fr": "Le cœur discret du vestiaire — des basiques épurés et minimalistes dans des tissus doux et durables, faits pour être portés en boucle.",
    },
    "gift-ideas": {
        "mood": "gift_ready", "season": "gifts",
        "subtitle": "Ready to gift", "seo_title": "Gift Ideas — ready to gift",
        "meta_description": "Thoughtful, gift-ready pieces for someone with great taste.",
        "editorial_intro": "Pieces that land well as a gift — characterful prints and easy staples, printed on demand and shipped with care.",
        "editorial_intro_it": "Capi perfetti da regalare — stampe con carattere e basici facili, stampati su ordinazione e spediti con cura.",
        "editorial_intro_fr": "Des pièces qui font de jolis cadeaux — des imprimés pleins de caractère et des basiques faciles, imprimés à la demande et expédiés avec soin.",
    },
}


class Command(BaseCommand):
    help = "Fill mood/season/editorial on existing collections (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        from merchandising.models import Collection
        examined = changed = 0
        for slug, fields in DATA.items():
            c = Collection.objects.filter(slug=slug).first()
            if not c:
                continue
            examined += 1
            touched = False
            for key, val in fields.items():
                if not (getattr(c, key, "") or "").strip():   # only fill empties
                    setattr(c, key, val); touched = True
            if touched:
                changed += 1
                if opts["apply"]:
                    c.save()
        mode = "APPLIED" if opts["apply"] else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] matched={examined} updated={changed}"))
        if not opts["apply"] and changed:
            self.stdout.write(self.style.NOTICE("Re-run with --apply to write."))
