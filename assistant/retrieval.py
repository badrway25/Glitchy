"""Lightweight, dependency-free retrieval over the curated knowledge base and the
product catalog. Keyword/token overlap scoring — no external embedding service,
so it works offline and never leaks data off-site."""
import re

from .models import KnowledgeEntry

_STOP = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "i", "to", "of", "for",
    "can", "you", "your", "my", "me", "and", "or", "in", "on", "it", "this", "that",
    "il", "lo", "la", "le", "un", "una", "di", "e", "che", "come", "posso", "puo",
    "the", "je", "tu", "le", "la", "les", "un", "une", "de", "et", "que", "comment",
    "puis", "vous", "est", "sont", "quel", "quels", "quelle",
}


def _tokens(text):
    # \w is Unicode-aware in Python 3 (matches accented letters too).
    return [t for t in re.findall(r"\w+", (text or "").lower(), re.UNICODE)
            if len(t) > 1 and t not in _STOP]


def retrieve_knowledge(query, limit=5):
    """Return the most relevant active KnowledgeEntry objects for a query."""
    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    scored = []
    for entry in KnowledgeEntry.objects.filter(is_active=True):
        blob = entry.search_blob()
        blob_tokens = set(_tokens(blob))
        overlap = len(q_tokens & blob_tokens)
        # boost for category name appearing in the query
        if entry.category in query.lower():
            overlap += 2
        if overlap:
            scored.append((overlap + entry.priority * 0.1, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]


def retrieve_faqs(query, limit=5):
    """Active product + general FAQs relevant to a query (used as assistant context
    alongside the curated knowledge base)."""
    from store.models import GeneralFAQ, ProductFAQ  # local import to avoid load cycles

    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    scored = []
    for model in (ProductFAQ, GeneralFAQ):
        for f in model.objects.filter(is_active=True):
            blob = " ".join(filter(None, [f.question, f.question_it, f.question_fr,
                                           f.answer, f.answer_it, f.answer_fr])).lower()
            overlap = len(q_tokens & set(_tokens(blob)))
            if overlap:
                scored.append((overlap, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:limit]]


def retrieve_products(query, limit=4):
    """Return catalog products relevant to the query (name/description/category)."""
    from store.models import Product  # local import to avoid app-load cycles

    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    scored = []
    for p in Product.objects.filter(is_available=True).select_related("category"):
        blob = " ".join(filter(None, [
            p.product_name, getattr(p, "description", ""),
            getattr(p, "composition", ""), getattr(p, "care_instructions", ""),
            p.category.category_name if p.category_id else "",
        ])).lower()
        overlap = len(q_tokens & set(_tokens(blob)))
        if overlap:
            scored.append((overlap, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def is_in_scope(query):
    """Heuristic: does the query plausibly relate to the store at all?
    Used only as a soft signal — the LLM guardrails are the real gate."""
    if retrieve_knowledge(query, limit=1) or retrieve_products(query, limit=1):
        return True
    scope_words = (
        "ship", "deliver", "return", "refund", "size", "fit", "wash", "care", "fabric",
        "material", "pay", "payment", "card", "stripe", "paypal", "order", "track",
        "account", "guest", "checkout", "cart", "price", "cost", "product", "tee",
        "shirt", "jeans", "store", "shop", "buy", "coupon", "discount", "stock",
        "spediz", "consegn", "reso", "resi", "rimbors", "taglia", "paga", "ordine",
        "traccia", "carrello", "prezzo", "prodotto", "negoz", "livr", "retour",
        "rembours", "taille", "paie", "commande", "suivi", "panier", "prix",
    )
    ql = (query or "").lower()
    return any(w in ql for w in scope_words)


def store_facts(query, lang="en"):
    """REAL store facts injected for every in-scope question, so the model always has
    grounded material for the core topics (empty-KB deployments used to repeat the
    decline sentence for perfectly normal questions).

    Sources: the SAME shipping rate table the checkout charges from, the payment
    resolver availability flags, the public return-window setting. No secrets, no
    internal costs, no PII.
    """
    from django.conf import settings
    lines = []
    try:
        from shipping.constants import COUNTRY_NAMES
        from shipping.services import fallback_quote
        ql = (query or "").lower()
        _LOCAL_NAMES = {
            "IT": ("italia", "italy", "italie"), "FR": ("francia", "france"),
            "BE": ("belgio", "belgium", "belgique"), "DE": ("germania", "germany", "allemagne"),
            "ES": ("spagna", "spain", "espagne"), "NL": ("olanda", "netherlands", "pays-bas"),
            "PT": ("portogallo", "portugal"), "CH": ("svizzera", "switzerland", "suisse"),
            "AT": ("austria", "autriche"), "IE": ("irlanda", "ireland", "irlande"),
            "GB": ("regno unito", "uk", "united kingdom", "royaume-uni", "inghilterra"),
            "US": ("stati uniti", "usa", "united states", "etats-unis"),
            "CA": ("canada",), "AU": ("australia", "australie"),
        }
        code = ""
        for cc, names in _LOCAL_NAMES.items():
            if any(n in ql for n in names):
                code = cc
                break
        codes = [code] if code else ["IT", "FR"]
        for cc in codes:
            fq = fallback_quote(cc, total_quantity=1, subtotal=0.0)
            if fq.available:
                nm = COUNTRY_NAMES.get(cc, cc)
                extra = ""
                thr = getattr(fq, "free_threshold", None)
                if thr:
                    extra = f", free over EUR {thr:.0f}"
                lines.append(f"Shipping to {nm}: cost EUR {fq.cost:.2f}{extra}, "
                             f"estimated {fq.eta_label}.")
    except Exception:
        pass
    try:
        from payments import config as pconf
        methods = []
        if pconf.stripe_secret_key() and pconf.stripe_publishable_key():
            methods.append("credit/debit card (Stripe)")
        if pconf.paypal_available():
            methods.append("PayPal")
        if methods:
            lines.append("Payment methods available at checkout: " + ", ".join(methods) + ".")
        lines.append("Payment issues: suggest retrying, trying the other method, or "
                     "contacting support. Never ask for card numbers in chat.")
    except Exception:
        pass
    days = getattr(settings, "RETURN_WINDOW_DAYS", None)
    if days:
        lines.append(f"Returns: customers can request a return within {days} days; "
                     "the returns page has the step-by-step procedure.")
    support = getattr(settings, "SUPPORT_EMAIL", "")
    if support:
        lines.append(f"Support contact: {support}.")
    return chr(10).join(lines)
