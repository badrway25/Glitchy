"""Handing a conversation over to a human, gracefully.

When the assistant declines or answers without grounding, it should not leave the
shopper at a dead end. It offers the contact page with the right category already
selected — a link, never an automatic send. Nothing from the conversation travels
in the URL: only a category keyword, so no personal data or card number can leak
into a query string, a referrer header or an access log.
"""
from __future__ import annotations

from django.urls import reverse

#: keyword → contact category. Deliberately small and conservative: an unclear
#: question becomes "other" rather than being mis-routed.
_RULES = (
    ("payment", ("payment", "paypal", "stripe", "card", "charged", "refund failed",
                 "pagamento", "carta", "paiement", "carte")),
    ("delivery", ("delivery", "tracking", "parcel", "shipment", "where is my order",
                  "not arrived", "consegna", "spedizione", "livraison", "colis")),
    ("returns", ("return", "refund", "exchange", "send back", "reso", "rimborso",
                 "retour", "remboursement")),
    ("order", ("order status", "my order", "order number", "cancel my order",
               "ordine", "commande")),
    ("product", ("size", "sizing", "fabric", "material", "fit", "colour", "color",
                 "taglia", "tessuto", "taille", "tissu")),
)

DEFAULT_CATEGORY = "other"


def guess_category(text) -> str:
    """Best-effort contact category for a question. Never raises, never guesses wildly."""
    low = str(text or "").lower()
    if not low.strip():
        return DEFAULT_CATEGORY
    for category, keywords in _RULES:
        if any(keyword in low for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


def contact_url_for(text=None, category=None) -> str:
    """URL of the contact page with the category pre-selected.

    Only the category is ever appended — the shopper's words stay out of the URL."""
    try:
        base = reverse("contact")
    except Exception:
        base = "/contact/"
    chosen = category or guess_category(text)
    if chosen and chosen != DEFAULT_CATEGORY:
        return f"{base}?category={chosen}"
    return base
