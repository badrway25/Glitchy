"""Lightweight message-language detection — no external calls, no second model.

The assistant must answer in the language of the USER'S LATEST MESSAGE (not the site
locale): heuristic stopword scoring for it/fr/en + Unicode-range detection for Arabic.
Falls back to the current site language when the message is too short/ambiguous.
"""
import re

_AR_RE = re.compile(r"[؀-ۿݐ-ݿ]")

_STOPWORDS = {
    "it": {"il", "lo", "la", "le", "gli", "un", "una", "che", "chi", "come", "cosa", "dove",
           "quando", "quanto", "quanta", "quali", "sono", "ho", "hai", "mio", "mia", "miei",
           "per", "con", "non", "del", "della", "dei", "questo", "questa", "posso", "puoi",
           "vorrei", "grazie", "ciao", "funziona", "aiuto", "ordine", "consegna", "spedizione",
           "reso", "pagamento", "carrello", "tempo", "mette", "costa", "perché", "più", "è"},
    "fr": {"le", "la", "les", "un", "une", "des", "que", "qui", "comment", "quoi", "où",
           "quand", "combien", "quels", "quelles", "suis", "j'ai", "mon", "ma", "mes", "pour",
           "avec", "pas", "du", "de", "ce", "cette", "je", "peux", "pouvez", "voudrais",
           "merci", "bonjour", "marche", "aide", "commande", "livraison", "retour", "paiement",
           "panier", "délais", "coûte", "pourquoi", "est"},
    "en": {"the", "a", "an", "that", "who", "how", "what", "where", "when", "much", "many",
           "which", "am", "have", "my", "for", "with", "not", "of", "this", "i", "can", "you",
           "would", "thanks", "hello", "works", "help", "order", "delivery", "shipping",
           "return", "payment", "cart", "time", "takes", "cost", "why", "is", "does", "do"},
}

_NAMES = {"it": "Italian", "fr": "French", "en": "English", "ar": "Arabic"}


def detect_language(message, site_lang="en"):
    """Return 'it' | 'fr' | 'en' | 'ar' for the message, site language when ambiguous."""
    text = (message or "").strip()
    if not text:
        return site_lang if site_lang in _NAMES else "en"
    if _AR_RE.search(text):
        return "ar"
    words = re.findall(r"[a-zàâáäèêéëìîíïòôóöùûúü']+", text.lower())
    if not words:
        return site_lang if site_lang in _NAMES else "en"
    scores = {lang: sum(1 for w in words if w in sw) for lang, sw in _STOPWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return site_lang if site_lang in _NAMES else "en"
    # tie-break in favour of the site language
    top = [l for l, sc in scores.items() if sc == scores[best]]
    if len(top) > 1 and site_lang in top:
        return site_lang
    return best


def language_name(code):
    return _NAMES.get(code, "English")
