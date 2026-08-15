"""Orchestrates a single assistant turn: retrieve site context, build a
guardrailed prompt, call the LLM (or fall back), and persist the conversation.

Privacy: order/tracking context is included ONLY for the authenticated owner of
the order. Guests never receive order data.
"""
import hashlib
import logging

from django.conf import settings
from django.utils import timezone

from . import prompt as prompt_mod
from . import retrieval
from .models import AssistantConversation, AssistantMessage
from .providers import FallbackProvider, ProviderError, get_provider

logger = logging.getLogger("assistant")

SUPPORTED_LANGS = ("en", "it", "fr")


def hash_ip(ip):
    if not ip:
        return ""
    salt = (getattr(settings, "SECRET_KEY", "") or "")[:16]
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def _order_context_for(request, query, lang):
    """Return a short summary of the requester's OWN recent orders, only if they
    are authenticated and the question is about orders/tracking. Never others'."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    ql = query.lower()
    triggers = ("order", "track", "tracking", "delivery", "shipped", "where is",
                "ordine", "traccia", "spediz", "consegn", "dov", "commande",
                "suivi", "livr")
    if not any(t in ql for t in triggers):
        return None
    try:
        from orders.models import Order
        orders = Order.objects.filter(user=user, is_ordered=True).order_by("-created_at")[:3]
    except Exception:
        return None
    if not orders:
        return None
    lines = []
    for o in orders:
        lines.append(f"Order #{o.order_number}: status {o.status}, "
                     f"placed {o.created_at:%Y-%m-%d}, total {o.order_total}.")
    return "\n".join(lines)


def get_or_create_conversation(request):
    if not request.session.session_key:
        request.session.save()
    sk = request.session.session_key or ""
    lang = (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    conv_id = request.session.get("assistant_conversation_id")
    conv = None
    if conv_id:
        conv = AssistantConversation.objects.filter(id=conv_id, session_key=sk).first()
    if conv is None:
        ip = request.META.get("REMOTE_ADDR", "")
        conv = AssistantConversation.objects.create(
            session_key=sk,
            account=request.user if request.user.is_authenticated else None,
            language=lang,
            ip_hash=hash_ip(ip),
        )
        request.session["assistant_conversation_id"] = conv.id
    return conv, lang



_SENSITIVE_PATTERNS = (
    # raw database / SQL
    "select ", "select*", "drop table", "sql", "database", "tabella", "table payments",
    "raw query", "query sql",
    # all users / other customers
    "tutti gli ordini", "all orders", "toutes les commandes", "email utenti", "user emails",
    "all users", "tutti gli utenti", "altro cliente", "another customer", "other user",
    "tous les utilisateurs", "tous les clients", "emails des utilisateurs",
    "un autre client", "facturation interne", "ignore les regles", "ignore les règles",
    "cle stripe", "clé stripe", "base de donnees", "base de données",
    "di un altro",
    # secrets / credentials / admin
    "api key", "chiave stripe", "stripe key", "secret", "segreto", "password", "token",
    "credenzial", "credential", "admin", "webhook",
    # internal billing / margins
    "fatturazione interna", "internal billing", "margini", "margins", "printify cost",
    "costi printify", "provider config",
    # memory exfiltration / storing sensitive data
    "ricordati la mia carta", "ricorda la mia carta", "remember my card", "save my card",
    "numero di carta", "card number", "numéro de carte", "memorizza la password",
    "cosa ha chiesto", "what did the other", "altro utente ha chiesto", "other user asked",
    # prompt injection
    "ignora le regole", "ignore the rules", "ignore previous", "ignora le istruzioni",
    "system prompt", "le tue istruzioni", "your instructions", "jailbreak",
)


def sensitive_block(query):
    """True for questions that must be refused BEFORE any retrieval or LLM call:
    raw DB/SQL, other users' data, secrets/admin/config, internal billing, injection."""
    ql = (query or "").lower()
    return any(p in ql for p in _SENSITIVE_PATTERNS)


_REFUSALS = {
    "en": ("I can't access sensitive account, database or admin data — I can help with "
           "products, shipping, payments and your own orders. For anything else, our "
           "support team is happy to help."),
    "it": ("Non posso accedere a dati sensibili di account, database o amministrazione — "
           "posso aiutarti con prodotti, spedizioni, pagamenti e i tuoi ordini. Per il "
           "resto, il nostro supporto è a disposizione."),
    "fr": ("Je ne peux pas accéder aux données sensibles de compte, base de données ou "
           "administration — je peux vous aider avec les produits, la livraison, les "
           "paiements et vos propres commandes. Pour le reste, notre support est là."),
    "ar": ("لا يمكنني الوصول إلى بيانات الحساب أو قاعدة البيانات أو الإدارة الحساسة — "
           "يمكنني مساعدتك في المنتجات والشحن والمدفوعات وطلباتك الخاصة."),
}


def sensitive_refusal(lang):
    return _REFUSALS.get(lang, _REFUSALS["en"])

def answer_question(request, query):
    # HARD SECURITY GATE — refuse sensitive scopes before retrieval, context or LLM.
    if sensitive_block(query):
        conv0, lang0 = get_or_create_conversation(request)
        AssistantMessage.objects.create(conversation=conv0, role="user", content=query[:600])
        from .language import detect_language
        return _finalise(conv0, sensitive_refusal(detect_language(query, site_lang=lang0)),
                         provider="guardrail", grounded=False, sources=[],
                         question=query)
    """Main entry point. Returns a dict the view serialises to JSON."""
    query = (query or "").strip()
    conv, lang = get_or_create_conversation(request)

    AssistantMessage.objects.create(conversation=conv, role="user", content=query[:1000])

    knowledge = retrieval.retrieve_knowledge(query, limit=5)
    faqs = retrieval.retrieve_faqs(query, limit=4)
    products = retrieval.retrieve_products(query, limit=4)
    if not products:
        products = _followup_products(conv)          # conversational memory for follow-ups
    order_ctx = _order_context_for(request, query, lang)
    in_scope = bool(knowledge or faqs or products or order_ctx) or retrieval.is_in_scope(query)

    decline = prompt_mod.decline_message(lang)
    sources = ([f"kb:{k.key}" for k in knowledge] + [f"faq:{f.id}" for f in faqs] +
               [f"product:{p.id}" for p in products])
    knowledge = list(knowledge) + list(faqs)   # FAQs grounded alongside the KB

    # Out of scope and nothing to ground on -> decline immediately (no LLM call).
    if not in_scope:
        return _finalise(conv, decline, provider="guardrail", grounded=False, sources=[],
                         question=query)

    # Surface real, active collections so the assistant can recommend them (never invented).
    collections = []
    try:
        from merchandising.models import Collection
        collections = [c for c in Collection.objects.filter(is_active=True)[:6]
                       if c.active_products().exists()]
    except Exception:
        collections = []
    facts = retrieval.store_facts(query, lang)
    context = prompt_mod.build_context(knowledge, products, lang, order_ctx,
                                       collections=collections, store_facts=facts)
    from .language import detect_language
    msg_lang = detect_language(query, site_lang=lang)
    system_prompt = prompt_mod.build_system_prompt(context, lang, language_code=msg_lang)

    provider = get_provider()
    if provider is not None:
        history = _recent_history(conv)
        try:
            answer = provider.complete(system_prompt, history)
            grounded = decline.split(".")[0] not in answer
            return _finalise(conv, answer, provider=provider.name, products=products, language=msg_lang,
                             question=query, grounded=grounded, sources=sources)
        except ProviderError:
            pass  # fall through to curated fallback

    # Fallback: best curated answer (or decline). Always grounded, no API call.
    fb = FallbackProvider()
    smart = _smart_fallback_answer(query, msg_lang)
    if smart and not knowledge:
        answer = smart
    else:
        answer = fb.answer_from_knowledge(knowledge, lang, decline)
    grounded = bool(knowledge)
    return _finalise(conv, answer, provider="fallback", grounded=grounded, sources=sources,
                     products=products, question=query)


def _recent_history(conv, limit=6):
    msgs = list(conv.messages.order_by("-created_at")[:limit])
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs if m.role in ("user", "assistant")]


def _public_product_cards(products):
    """PUBLIC card data only: name, price, sale price, url, image. No internal costs,
    no provider ids — safe by construction for the chat UI."""
    cards = []
    for p in (products or [])[:3]:
        try:
            cards.append({
                "name": p.product_name,
                "price": float(p.price),
                "url": p.get_url(),
                "image": p.images.url if getattr(p, "images", None) else "",
            })
        except Exception:
            continue
    return cards


def _smart_fallback_answer(query, msg_lang):
    """Limited-mode answers for the CORE topics, built from real store data and localized.
    Returns None when the question is not one of the core topics (caller keeps its flow)."""
    ql = (query or "").lower()
    from django.conf import settings

    ship_words = ("spediz", "consegn", "deliver", "shipping", "livrais", "délais", "delais")
    pay_words = ("paga", "pagam", "pay", "paypal", "carta", "card", "stripe", "paie")
    ret_words = ("reso", "resi", "rimbors", "return", "refund", "retour", "rembours")

    if any(w in ql for w in ship_words):
        try:
            from shipping.constants import COUNTRY_NAMES
            from shipping.services import fallback_quote
            _NAMES = {"IT": ("italia", "italy", "italie"), "FR": ("francia", "france"),
                      "BE": ("belgio", "belgium", "belgique"), "DE": ("germania", "germany", "allemagne"),
                      "ES": ("spagna", "spain", "espagne"), "GB": ("regno unito", "uk", "royaume-uni"),
                      "US": ("stati uniti", "usa", "états-unis", "etats-unis"), "CH": ("svizzera", "suisse", "switzerland"),
                      "NL": ("olanda", "netherlands", "pays-bas"), "PT": ("portogallo", "portugal")}
            code = next((cc for cc, names in _NAMES.items() if any(n in ql for n in names)), "")
            if code:
                fq = fallback_quote(code, total_quantity=1, subtotal=0.0)
                if fq.available:
                    nm = COUNTRY_NAMES.get(code, code)
                    cost = f"{fq.cost:.2f}"
                    eta = str(fq.eta_label)
                    if msg_lang == "it":
                        return (f"Spediamo in {nm}: costo di spedizione {cost} EUR, consegna "
                                f"stimata {eta}. Il totale esatto lo vedi nel checkout prima "
                                f"di pagare.")
                    if msg_lang == "fr":
                        return (f"Nous livrons en {nm} : frais de livraison {cost} EUR, délai "
                                f"estimé {eta}. Le total exact apparaît au checkout avant le "
                                f"paiement.")
                    return (f"We ship to {nm}: shipping cost EUR {cost}, estimated delivery "
                            f"{eta}. The exact total is shown at checkout before you pay.")
        except Exception:
            pass
        if msg_lang == "it":
            return ("I tempi e i costi di spedizione dipendono dalla destinazione: li vedi "
                    "calcolati con precisione nel checkout prima di pagare. Dimmi il paese e "
                    "ti do la stima configurata.")
        if msg_lang == "fr":
            return ("Les délais et frais de livraison dépendent de la destination : ils sont "
                    "calculés précisément au checkout avant le paiement. Dites-moi le pays et "
                    "je vous donne l'estimation configurée.")
        return ("Shipping times and costs depend on the destination: they are calculated "
                "precisely at checkout before you pay. Tell me the country and I'll give you "
                "the configured estimate.")

    if any(w in ql for w in pay_words):
        methods = []
        try:
            from payments import config as pconf
            if pconf.stripe_secret_key() and pconf.stripe_publishable_key():
                methods.append("carta" if msg_lang == "it" else ("carte" if msg_lang == "fr" else "card"))
            if pconf.paypal_available():
                methods.append("PayPal")
        except Exception:
            pass
        mtxt = " e ".join(methods) if msg_lang == "it" else (" et ".join(methods) if msg_lang == "fr" else " and ".join(methods))
        if msg_lang == "it":
            base = (f"Al checkout puoi pagare con {mtxt}. " if methods else "")
            return (base + "Se un pagamento non va a buon fine: riprova, prova l'altro metodo "
                    "oppure scrivici — nessun addebito avviene senza la tua conferma.")
        if msg_lang == "fr":
            base = (f"Au checkout vous pouvez payer par {mtxt}. " if methods else "")
            return (base + "Si un paiement échoue : réessayez, essayez l'autre méthode ou "
                    "contactez-nous — aucun débit sans votre confirmation.")
        base = (f"At checkout you can pay with {mtxt}. " if methods else "")
        return (base + "If a payment fails: retry, try the other method, or contact us — "
                "nothing is charged without your confirmation.")

    if any(w in ql for w in ret_words):
        from django.conf import settings as st
        days = getattr(st, "RETURN_WINDOW_DAYS", 14)
        if msg_lang == "it":
            return (f"Puoi richiedere un reso entro {days} giorni. Trovi la procedura "
                    f"guidata nella pagina Resi; se serve una mano, il supporto è qui.")
        if msg_lang == "fr":
            return (f"Vous pouvez demander un retour sous {days} jours. La procédure guidée "
                    f"est sur la page Retours ; notre support reste disponible.")
        return (f"You can request a return within {days} days. The guided procedure is on "
                f"the Returns page; support is here if you need a hand.")
    return None


def _followup_products(conv, limit=4):
    """Products referenced by the PREVIOUS assistant turns — the conversational memory the
    retrieval layer was missing: 'quanto costa?' after a product search now reuses the
    products just shown instead of finding nothing and answering generically."""
    ids = []
    try:
        for m in conv.messages.filter(role="assistant").order_by("-created_at")[:3]:
            for src in (m.used_sources or []):
                if isinstance(src, str) and src.startswith("product:"):
                    try:
                        pid = int(src.split(":", 1)[1])
                        if pid not in ids:
                            ids.append(pid)
                    except ValueError:
                        continue
        if not ids:
            return []
        from store.models import Product
        found = {p.id: p for p in Product.objects.filter(id__in=ids[:limit], is_available=True)}
        return [found[i] for i in ids[:limit] if i in found]
    except Exception:
        return []


def _finalise(conv, answer, provider, grounded, sources, products=None, language="",
              question=""):
    msg = AssistantMessage.objects.create(
        conversation=conv, role="assistant", content=answer,
        provider=provider, grounded=grounded, used_sources=sources,
    )
    conv.save(update_fields=[]) if False else None
    out = {
        "answer": answer,
        "grounded": grounded,
        "provider": provider,
        "message_id": msg.id,
        "can_contact_support": not grounded,
    }
    if out["can_contact_support"]:
        # Point at a human instead of ending on "I don't know". Only a category
        # keyword travels in the URL — never the shopper's words.
        from .escalation import contact_url_for, guess_category
        out["contact_url"] = contact_url_for(question)
        out["contact_category"] = guess_category(question)
    if language:
        out["language"] = language
    if products:
        out["products"] = _public_product_cards(products)
    return out
