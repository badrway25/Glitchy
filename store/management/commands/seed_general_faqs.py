"""Seed the site-wide General FAQ (idempotent by question). EN/IT/FR."""
from django.core.management.base import BaseCommand

from store.models import GeneralFAQ

F = [
    ("shipping", 1, "How long does delivery take?",
     "Quanto dura la consegna?", "Quels sont les délais de livraison ?",
     "Orders are printed on demand and usually arrive within about 3–6 business days domestically, "
     "a little longer internationally. The exact estimate and cost are shown at checkout for your country.",
     "Gli ordini sono stampati su richiesta e di solito arrivano in circa 3–6 giorni lavorativi a livello "
     "nazionale, un po' di più all'estero. La stima e il costo esatti sono mostrati al checkout per il tuo paese.",
     "Les commandes sont imprimées à la demande et arrivent généralement sous 3 à 6 jours ouvrés en national, "
     "un peu plus à l'international. L'estimation et le coût exacts sont affichés au paiement pour votre pays."),
    ("shipping", 2, "Do you offer free shipping?",
     "Offrite la spedizione gratuita?", "Proposez-vous la livraison gratuite ?",
     "Yes — orders above the threshold shown in your cart ship free. You'll see a progress bar in the cart "
     "telling you how close you are.",
     "Sì — gli ordini sopra la soglia mostrata nel carrello hanno spedizione gratuita. Nel carrello vedi una "
     "barra di avanzamento che ti dice quanto manca.",
     "Oui — les commandes au-dessus du seuil indiqué dans votre panier sont livrées gratuitement. Une barre de "
     "progression dans le panier vous indique combien il vous reste."),
    ("returns", 1, "What is your return policy?",
     "Qual è la politica per i resi?", "Quelle est votre politique de retour ?",
     "You can return your order within 14 days of delivery, free and easy. Items should be unworn and in "
     "their original condition. Start a return from your account under \"My orders\" or the Returns page.",
     "Puoi restituire il tuo ordine entro 14 giorni dalla consegna, in modo gratuito e semplice. I capi devono "
     "essere non indossati e in condizioni originali. Avvia un reso dal tuo account in \"I miei ordini\" o dalla pagina Resi.",
     "Vous pouvez retourner votre commande sous 14 jours après livraison, gratuitement. Les articles doivent être "
     "non portés et en état d'origine. Lancez un retour depuis votre compte dans « Mes commandes » ou la page Retours."),
    ("returns", 2, "When will I get my refund?",
     "Quando riceverò il rimborso?", "Quand serai-je remboursé ?",
     "Once your return is approved and received, we issue the refund to your original payment method. It usually "
     "appears within a few business days, depending on your bank.",
     "Una volta approvato e ricevuto il reso, emettiamo il rimborso sul metodo di pagamento originale. Di solito "
     "appare entro pochi giorni lavorativi, a seconda della tua banca.",
     "Une fois le retour approuvé et reçu, nous procédons au remboursement sur votre moyen de paiement d'origine. "
     "Il apparaît généralement sous quelques jours ouvrés, selon votre banque."),
    ("payments", 1, "Which payment methods do you accept?",
     "Quali metodi di pagamento accettate?", "Quels moyens de paiement acceptez-vous ?",
     "We accept major credit and debit cards through Stripe, and PayPal. Checkout is encrypted and secure — we "
     "never store your full card details.",
     "Accettiamo le principali carte di credito e debito tramite Stripe e PayPal. Il checkout è crittografato e "
     "sicuro: non memorizziamo mai i dati completi della tua carta.",
     "Nous acceptons les principales cartes via Stripe, ainsi que PayPal. Le paiement est chiffré et sécurisé — "
     "nous ne stockons jamais vos données de carte complètes."),
    ("orders", 1, "How do I track my order?",
     "Come traccio il mio ordine?", "Comment suivre ma commande ?",
     "When your order ships you'll receive an email with tracking. If you have an account, you can also see each "
     "order's status under \"My orders\".",
     "Quando il tuo ordine viene spedito riceverai un'email con il tracking. Se hai un account, puoi vedere lo "
     "stato di ogni ordine in \"I miei ordini\".",
     "Lorsque votre commande est expédiée, vous recevez un e-mail avec le suivi. Avec un compte, vous pouvez aussi "
     "voir le statut de chaque commande dans « Mes commandes »."),
    ("account", 1, "Can I buy without an account?",
     "Posso comprare senza un account?", "Puis-je acheter sans compte ?",
     "Yes — you can check out as a guest. You can optionally create an account afterwards to track orders and keep "
     "your saved items.",
     "Sì — puoi completare l'acquisto come ospite. Se vuoi, puoi creare un account in seguito per seguire gli ordini "
     "e conservare i tuoi articoli salvati.",
     "Oui — vous pouvez commander en tant qu'invité. Vous pourrez éventuellement créer un compte ensuite pour suivre "
     "vos commandes et conserver vos articles enregistrés."),
    ("account", 2, "How does the wishlist work?",
     "Come funziona la lista dei desideri?", "Comment fonctionne la liste de souhaits ?",
     "Tap the heart on any product to save it. Guests keep saved items on their device; logged-in customers keep "
     "them on their account under \"Saved items\".",
     "Tocca il cuore su qualsiasi prodotto per salvarlo. Gli ospiti conservano gli articoli sul dispositivo; i "
     "clienti registrati li trovano nel loro account in \"Articoli salvati\".",
     "Touchez le cœur sur un produit pour l'enregistrer. Les invités conservent leurs articles sur l'appareil ; les "
     "clients connectés les retrouvent dans leur compte sous « Articles enregistrés »."),
    ("sizing", 1, "How do I choose my size?",
     "Come scelgo la taglia?", "Comment choisir ma taille ?",
     "Use the Size guide on each product page to match your measurements. If you're between sizes, we generally "
     "suggest sizing up for a relaxed fit.",
     "Usa la Guida alle taglie su ogni pagina prodotto per confrontare le tue misure. Se sei tra due taglie, in "
     "genere consigliamo la taglia più grande per una vestibilità comoda.",
     "Utilisez le Guide des tailles sur chaque page produit pour comparer vos mesures. Entre deux tailles, nous "
     "conseillons généralement la taille au-dessus pour une coupe ample."),
    ("coupons", 1, "How do I use a promo code?",
     "Come uso un codice promo?", "Comment utiliser un code promo ?",
     "Enter your promo code in the cart and tap Apply. If it's valid, the discount appears in your order summary. "
     "We can't share or generate codes here — keep an eye on our newsletter for offers.",
     "Inserisci il codice promo nel carrello e tocca Applica. Se è valido, lo sconto appare nel riepilogo ordine. "
     "Non possiamo condividere o generare codici qui — segui la newsletter per le offerte.",
     "Saisissez votre code promo dans le panier et touchez Appliquer. S'il est valide, la remise apparaît dans le "
     "récapitulatif. Nous ne pouvons pas partager ou générer de codes ici — suivez la newsletter pour les offres."),
    ("support", 1, "How can I get help?",
     "Come posso ricevere aiuto?", "Comment obtenir de l'aide ?",
     "Use the assistant button at the bottom-right of any page, or the Contact link in the footer. For order-specific "
     "help, open the order in your account and use \"Need help with this order?\".",
     "Usa il pulsante dell'assistente in basso a destra in qualsiasi pagina, o il link Contatto nel footer. Per aiuto "
     "su un ordine specifico, apri l'ordine nel tuo account e usa \"Hai bisogno di aiuto con questo ordine?\".",
     "Utilisez le bouton de l'assistant en bas à droite, ou le lien Contact dans le pied de page. Pour une commande "
     "précise, ouvrez-la dans votre compte et utilisez « Besoin d'aide pour cette commande ? »."),
    ("sizing", 2, "Are products made to order?",
     "I prodotti sono fatti su richiesta?", "Les produits sont-ils fabriqués à la demande ?",
     "Yes — every piece is printed on demand when you order, using premium soft-touch materials. Less waste, and a "
     "fresh product made just for you.",
     "Sì — ogni capo è stampato su richiesta quando ordini, con materiali premium dal tatto morbido. Meno sprechi e "
     "un prodotto fresco fatto apposta per te.",
     "Oui — chaque pièce est imprimée à la demande lors de votre commande, avec des matières premium au toucher doux. "
     "Moins de gaspillage et un produit neuf rien que pour vous."),
]


class Command(BaseCommand):
    help = "Seed the site-wide general FAQ (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for cat, order, q, qit, qfr, a, ait, afr in F:
            _, was = GeneralFAQ.objects.update_or_create(
                question=q, defaults=dict(category=cat, order=order, question_it=qit,
                                          question_fr=qfr, answer=a, answer_it=ait,
                                          answer_fr=afr, is_active=True))
            created += int(was)
        self.stdout.write(self.style.SUCCESS(
            f"General FAQ seeded ({created} created, {GeneralFAQ.objects.count()} total)."))
