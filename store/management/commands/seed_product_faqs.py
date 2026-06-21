"""Seed a few safe, generic GLOBAL product FAQs (idempotent by question)."""
from django.core.management.base import BaseCommand

from store.models import ProductFAQ

FAQS = [
    dict(order=1,
         question="What materials are your products made from?",
         question_it="Di quali materiali sono fatti i vostri prodotti?",
         question_fr="En quels matériaux vos produits sont-ils fabriqués ?",
         answer="Our pieces use premium, soft-touch fabrics chosen for comfort and durability. "
                "Exact composition is listed under 'More information' on each product page.",
         answer_it="I nostri capi usano tessuti premium e dal tatto morbido, scelti per comfort e "
                   "resistenza. La composizione esatta è indicata in 'Maggiori informazioni' su ogni pagina prodotto.",
         answer_fr="Nos pièces utilisent des tissus premium au toucher doux, choisis pour le confort et "
                   "la durabilité. La composition exacte est indiquée sous « Plus d'informations » sur chaque page produit."),
    dict(order=2,
         question="How should I care for my item?",
         question_it="Come devo prendermi cura del capo?",
         question_fr="Comment entretenir mon article ?",
         answer="Machine wash cold and do not tumble dry to keep prints and fabric in great shape. "
                "Specific care notes appear on the product page when available.",
         answer_it="Lava in lavatrice a freddo e non asciugare in asciugatrice per mantenere stampe e tessuto "
                   "in ottime condizioni. Le indicazioni specifiche di cura, se disponibili, sono sulla pagina prodotto.",
         answer_fr="Lavez en machine à froid et ne séchez pas au sèche-linge pour préserver les impressions et le "
                   "tissu. Les conseils d'entretien spécifiques figurent sur la page produit lorsqu'ils sont disponibles."),
    dict(order=3,
         question="How do I find my size?",
         question_it="Come trovo la mia taglia?",
         question_fr="Comment trouver ma taille ?",
         answer="Use the Size guide on the product page to match your measurements. If you're between sizes, "
                "we generally suggest sizing up for a relaxed fit.",
         answer_it="Usa la Guida alle taglie nella pagina prodotto per confrontare le tue misure. Se sei tra due "
                   "taglie, in genere consigliamo la taglia più grande per una vestibilità comoda.",
         answer_fr="Utilisez le Guide des tailles sur la page produit pour comparer vos mesures. Entre deux tailles, "
                   "nous conseillons généralement la taille au-dessus pour une coupe ample."),
    dict(order=4,
         question="Are items made to order?",
         question_it="I capi sono fatti su richiesta?",
         question_fr="Les articles sont-ils fabriqués à la demande ?",
         answer="Yes — every piece is printed on demand when you order. This means less waste and a fresh product "
                "made just for you, so production takes a little time before shipping.",
         answer_it="Sì — ogni capo è stampato su richiesta quando ordini. Questo significa meno sprechi e un prodotto "
                   "fresco fatto apposta per te, quindi la produzione richiede un po' di tempo prima della spedizione.",
         answer_fr="Oui — chaque pièce est imprimée à la demande lors de votre commande. Moins de gaspillage et un "
                   "produit neuf rien que pour vous : la production prend donc un peu de temps avant l'expédition."),
]


class Command(BaseCommand):
    help = "Seed generic global product FAQs (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for data in FAQS:
            q = data["question"]
            _, was_created = ProductFAQ.objects.update_or_create(
                question=q, product__isnull=True, category__isnull=True, defaults=data)
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(
            f"Product FAQs seeded ({created} created, {ProductFAQ.objects.count()} total)."))
