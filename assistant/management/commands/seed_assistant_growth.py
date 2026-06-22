"""Seed assistant knowledge for the growth/shopping-mode topics (idempotent)."""
from django.core.management.base import BaseCommand

from assistant.models import KnowledgeEntry

ENTRIES = [
    dict(key="recommendations", category="shopping", priority=5,
         keywords="recommend suggestion choose help pick find product goes well match",
         question="Help me choose / what goes well with this?",
         question_it="Aiutami a scegliere / cosa sta bene con questo?",
         question_fr="Aidez-moi à choisir / qu'est-ce qui va bien avec ?",
         answer="On each product page you'll find 'Complete the look' and 'Recommended for you' "
                "with real pieces from our catalogue. You can also take our Style quiz for tailored picks. "
                "I can only point you to products that actually exist on the site.",
         answer_it="Su ogni pagina prodotto trovi 'Completa il look' e 'Consigliati per te' con capi reali "
                   "del nostro catalogo. Puoi anche fare lo Style quiz per suggerimenti su misura. Posso indicarti "
                   "solo prodotti realmente presenti sul sito.",
         answer_fr="Sur chaque page produit, vous trouverez « Complétez le look » et « Recommandé pour vous » "
                   "avec de vraies pièces de notre catalogue. Vous pouvez aussi faire notre Style quiz. Je ne peux "
                   "indiquer que des produits réellement présents sur le site."),
    dict(key="style_quiz", category="shopping", priority=4,
         keywords="style quiz find match guide recommend choose help",
         question="How does the style quiz work?",
         question_it="Come funziona lo style quiz?",
         question_fr="Comment fonctionne le style quiz ?",
         answer="The Style quiz asks a few quick questions (category, budget, colour, occasion) and suggests "
                "matching products from our real catalogue — no personal data needed. Find it in the footer.",
         answer_it="Lo Style quiz fa qualche domanda veloce (categoria, budget, colore, occasione) e suggerisce "
                   "prodotti corrispondenti dal nostro catalogo reale — senza dati personali. Lo trovi nel footer.",
         answer_fr="Le Style quiz pose quelques questions rapides (catégorie, budget, couleur, occasion) et propose "
                   "des produits correspondants de notre vrai catalogue — sans données personnelles. Dans le pied de page."),
    dict(key="collections", category="shopping", priority=4,
         keywords="collection collections edit curated new season essentials gift ideas",
         question="Do you have collections or gift ideas?",
         question_it="Avete collezioni o idee regalo?",
         question_fr="Avez-vous des collections ou des idées cadeaux ?",
         answer="Yes — see the Collections page (New Season, Essentials, Gift Ideas and more), each grouping "
                "real products. I can't invent products or discounts, but I can point you to these edits.",
         answer_it="Sì — vedi la pagina Collezioni (Nuova stagione, Essenziali, Idee regalo e altro), ognuna con "
                   "prodotti reali. Non posso inventare prodotti o sconti, ma posso indicarti queste selezioni.",
         answer_fr="Oui — voir la page Collections (Nouvelle saison, Essentiels, Idées cadeaux, etc.), chacune avec "
                   "de vrais produits. Je ne peux pas inventer de produits ni de remises, mais je peux vous orienter."),
    dict(key="complete_look", category="shopping", priority=4,
         keywords="complete look outfit bundle together style add selected match goes with",
         question="What is 'Complete the look'?",
         question_it="Cos'è 'Completa il look'?",
         question_fr="Qu'est-ce que « Complétez le look » ?",
         answer="On a product page, 'Complete the look' shows pieces that style well together; you can tick the "
                "ones you want and add them to your cart in one tap. Only real, available products are shown.",
         answer_it="Sulla pagina prodotto, 'Completa il look' mostra capi che stanno bene insieme; puoi selezionare "
                   "quelli che vuoi e aggiungerli al carrello con un tap. Sono mostrati solo prodotti reali e disponibili.",
         answer_fr="Sur une page produit, « Complétez le look » montre des pièces qui vont bien ensemble ; cochez "
                   "celles que vous voulez et ajoutez-les au panier en un geste. Seuls de vrais produits disponibles sont montrés."),
]


class Command(BaseCommand):
    help = "Seed shopping-mode assistant knowledge (idempotent)."

    def handle(self, *args, **options):
        n = 0
        for e in ENTRIES:
            _, created = KnowledgeEntry.objects.update_or_create(
                key=e["key"], defaults={**e, "is_active": True})
            n += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"Shopping KB seeded ({n} created, {KnowledgeEntry.objects.count()} total)."))
