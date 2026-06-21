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
