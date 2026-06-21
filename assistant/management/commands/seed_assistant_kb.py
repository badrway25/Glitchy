"""Seed the assistant knowledge base with curated, multilingual policy/FAQ entries.
Idempotent: re-running updates existing entries by key."""
from django.conf import settings
from django.core.management.base import BaseCommand

from assistant.models import KnowledgeEntry


def _entries():
    days = getattr(settings, "RETURN_WINDOW_DAYS", 14)
    return [
        dict(key="shipping-times", category="shipping", priority=10,
             keywords="shipping,delivery,how long,days,ship,spedizione,consegna,tempi,livraison,delai",
             question="How long does shipping take?",
             question_it="Quanto dura la spedizione?",
             question_fr="Quels sont les délais de livraison ?",
             answer="Orders are printed on demand and usually arrive within about 3–6 business days "
                    "for domestic destinations, a little longer internationally. The exact estimate and "
                    "cost are shown at checkout for your country.",
             answer_it="Gli ordini sono stampati su richiesta e di solito arrivano in circa 3–6 giorni "
                       "lavorativi per le destinazioni nazionali, un po' di più all'estero. La stima e il "
                       "costo esatti sono mostrati al checkout per il tuo paese.",
             answer_fr="Les commandes sont imprimées à la demande et arrivent généralement sous 3 à 6 jours "
                       "ouvrés en national, un peu plus à l'international. L'estimation et le coût exacts "
                       "sont affichés au paiement pour votre pays."),
        dict(key="returns-window", category="returns", priority=10,
             keywords="returns,return,send back,resi,reso,restituire,retours,retour,renvoyer",
             question="How do returns work?",
             question_it="Come funzionano i resi?",
             question_fr="Comment fonctionnent les retours ?",
             answer=f"You can return your order within {days} days of delivery, free and easy. Items should be "
                    f"unworn and in their original condition. Start a return from your account under "
                    f"\"My orders\", or from the Returns page.",
             answer_it=f"Puoi restituire il tuo ordine entro {days} giorni dalla consegna, in modo gratuito e "
                       f"semplice. I capi devono essere non indossati e in condizioni originali. Avvia un reso "
                       f"dal tuo account in \"I miei ordini\" o dalla pagina Resi.",
             answer_fr=f"Vous pouvez retourner votre commande sous {days} jours après livraison, gratuitement. "
                       f"Les articles doivent être non portés et en état d'origine. Lancez un retour depuis votre "
                       f"compte dans « Mes commandes » ou depuis la page Retours."),
        dict(key="refunds", category="refunds", priority=8,
             keywords="refund,money back,rimborso,refund,remboursement,argent",
             question="When do I get my refund?",
             question_it="Quando ricevo il rimborso?",
             question_fr="Quand vais-je être remboursé ?",
             answer="Once your return is approved and received, we issue the refund to your original payment "
                    "method. It typically appears within a few business days depending on your bank.",
             answer_it="Una volta approvato e ricevuto il reso, emettiamo il rimborso sul metodo di pagamento "
                       "originale. Di solito appare entro pochi giorni lavorativi, a seconda della tua banca.",
             answer_fr="Une fois le retour approuvé et reçu, nous procédons au remboursement sur votre moyen de "
                       "paiement d'origine. Il apparaît généralement sous quelques jours ouvrés selon votre banque."),
        dict(key="payments", category="payments", priority=8,
             keywords="payment,pay,card,stripe,paypal,visa,mastercard,pagamento,pagare,carta,paiement,payer",
             question="Which payment methods do you accept?",
             question_it="Quali metodi di pagamento accettate?",
             question_fr="Quels moyens de paiement acceptez-vous ?",
             answer="We accept major credit and debit cards through Stripe, and PayPal. Checkout is encrypted "
                    "and secure — we never store your full card details.",
             answer_it="Accettiamo le principali carte di credito e debito tramite Stripe e PayPal. Il checkout "
                       "è crittografato e sicuro: non memorizziamo mai i dati completi della tua carta.",
             answer_fr="Nous acceptons les principales cartes via Stripe, ainsi que PayPal. Le paiement est "
                       "chiffré et sécurisé — nous ne stockons jamais vos données de carte complètes."),
        dict(key="guest-checkout", category="account", priority=7,
             keywords="guest,without account,no account,ospite,senza account,invite,sans compte",
             question="Can I buy as a guest?",
             question_it="Posso comprare come ospite?",
             question_fr="Puis-je acheter en tant qu'invité ?",
             answer="Yes — you can check out as a guest without creating an account. You can optionally create "
                    "an account afterwards to track your orders.",
             answer_it="Sì — puoi completare l'acquisto come ospite senza creare un account. Se vuoi, puoi "
                       "creare un account in seguito per seguire i tuoi ordini.",
             answer_fr="Oui — vous pouvez commander en tant qu'invité sans créer de compte. Vous pourrez "
                       "éventuellement créer un compte ensuite pour suivre vos commandes."),
        dict(key="sizing", category="sizing", priority=7,
             keywords="size,sizing,fit,measure,taglia,vestibilita,misura,taille,coupe,mesure",
             question="How do I choose my size?",
             question_it="Come scelgo la taglia?",
             question_fr="Comment choisir ma taille ?",
             answer="Each product page shows the available sizes. Use the Size guide on the product page to "
                    "match your measurements. If you're between sizes, we generally suggest sizing up for a "
                    "relaxed fit.",
             answer_it="Ogni pagina prodotto mostra le taglie disponibili. Usa la Guida alle taglie nella "
                       "pagina prodotto per confrontare le tue misure. Se sei tra due taglie, in genere "
                       "consigliamo la taglia più grande per una vestibilità comoda.",
             answer_fr="Chaque page produit indique les tailles disponibles. Utilisez le Guide des tailles sur "
                       "la page produit pour comparer vos mesures. Entre deux tailles, nous conseillons "
                       "généralement la taille au-dessus pour une coupe ample."),
        dict(key="tracking", category="tracking", priority=6,
             keywords="track,tracking,where is my order,traccia,tracciamento,suivi,suivre",
             question="Where do I find my tracking?",
             question_it="Dove trovo il tracking?",
             question_fr="Où trouver le suivi de ma commande ?",
             answer="When your order ships you'll receive an email with tracking. If you have an account, you "
                    "can also see each order's status under \"My orders\".",
             answer_it="Quando il tuo ordine viene spedito riceverai un'email con il tracking. Se hai un "
                       "account, puoi anche vedere lo stato di ogni ordine in \"I miei ordini\".",
             answer_fr="Lorsque votre commande est expédiée, vous recevez un e-mail avec le suivi. Avec un "
                       "compte, vous pouvez aussi voir le statut de chaque commande dans « Mes commandes »."),
        dict(key="on-demand", category="ondemand", priority=5,
             keywords="print on demand,printify,made,quality,sustainable,on demand,su richiesta,demande",
             question="Are products made to order?",
             question_it="I prodotti sono fatti su richiesta?",
             question_fr="Les produits sont-ils fabriqués à la demande ?",
             answer="Yes. Every piece is printed on demand when you order, using premium, soft-touch materials. "
                    "This means less waste and a fresh product made just for you.",
             answer_it="Sì. Ogni capo è stampato su richiesta quando ordini, con materiali premium e dal tatto "
                       "morbido. Questo significa meno sprechi e un prodotto fresco fatto apposta per te.",
             answer_fr="Oui. Chaque pièce est imprimée à la demande lors de votre commande, avec des matières "
                       "premium au toucher doux. Moins de gaspillage et un produit neuf rien que pour vous."),
        dict(key="support", category="support", priority=5,
             keywords="support,contact,help,human,assistenza,contatto,aiuto,support,contact,aide",
             question="How do I contact support?",
             question_it="Come contatto il supporto?",
             question_fr="Comment contacter le support ?",
             answer="Our support team is happy to help. Use the Contact link in the footer, or I can help you "
                    "send a support request right here.",
             answer_it="Il nostro team di supporto è felice di aiutarti. Usa il link Contatto nel footer, "
                       "oppure posso aiutarti a inviare una richiesta di supporto da qui.",
             answer_fr="Notre équipe de support est là pour vous aider. Utilisez le lien Contact dans le pied "
                       "de page, ou je peux vous aider à envoyer une demande de support ici."),
        dict(key="secure-checkout", category="payments", priority=4,
             keywords="secure,safe,encryption,privacy,sicuro,sicurezza,securise,confidentialite",
             question="Is checkout secure?",
             question_it="Il checkout è sicuro?",
             question_fr="Le paiement est-il sécurisé ?",
             answer="Yes. Payments are processed over an encrypted connection by Stripe/PayPal. We don't store "
                    "your full card number, and your data is handled according to our privacy policy.",
             answer_it="Sì. I pagamenti sono elaborati su connessione crittografata da Stripe/PayPal. Non "
                       "memorizziamo il numero completo della carta e i tuoi dati sono trattati secondo la "
                       "nostra privacy policy.",
             answer_fr="Oui. Les paiements sont traités via une connexion chiffrée par Stripe/PayPal. Nous ne "
                       "stockons pas votre numéro de carte complet et vos données sont traitées selon notre "
                       "politique de confidentialité."),
    ]


class Command(BaseCommand):
    help = "Seed/refresh the assistant knowledge base (idempotent)."

    def handle(self, *args, **options):
        created = updated = 0
        for data in _entries():
            key = data.pop("key")
            obj, was_created = KnowledgeEntry.objects.update_or_create(key=key, defaults=data)
            created += int(was_created)
            updated += int(not was_created)
        self.stdout.write(self.style.SUCCESS(
            f"Knowledge base seeded: {created} created, {updated} updated, "
            f"{KnowledgeEntry.objects.count()} total."))
