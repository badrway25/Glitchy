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


def answer_question(request, query):
    """Main entry point. Returns a dict the view serialises to JSON."""
    query = (query or "").strip()
    conv, lang = get_or_create_conversation(request)

    AssistantMessage.objects.create(conversation=conv, role="user", content=query[:1000])

    knowledge = retrieval.retrieve_knowledge(query, limit=5)
    faqs = retrieval.retrieve_faqs(query, limit=4)
    products = retrieval.retrieve_products(query, limit=4)
    order_ctx = _order_context_for(request, query, lang)
    in_scope = bool(knowledge or faqs or products or order_ctx) or retrieval.is_in_scope(query)

    decline = prompt_mod.decline_message(lang)
    sources = ([f"kb:{k.key}" for k in knowledge] + [f"faq:{f.id}" for f in faqs] +
               [f"product:{p.id}" for p in products])
    knowledge = list(knowledge) + list(faqs)   # FAQs grounded alongside the KB

    # Out of scope and nothing to ground on -> decline immediately (no LLM call).
    if not in_scope:
        return _finalise(conv, decline, provider="guardrail", grounded=False, sources=[])

    context = prompt_mod.build_context(knowledge, products, lang, order_ctx)
    system_prompt = prompt_mod.build_system_prompt(context, lang)

    provider = get_provider()
    if provider is not None:
        history = _recent_history(conv)
        try:
            answer = provider.complete(system_prompt, history)
            grounded = decline.split(".")[0] not in answer
            return _finalise(conv, answer, provider=provider.name,
                             grounded=grounded, sources=sources)
        except ProviderError:
            pass  # fall through to curated fallback

    # Fallback: best curated answer (or decline). Always grounded, no API call.
    fb = FallbackProvider()
    answer = fb.answer_from_knowledge(knowledge, lang, decline)
    grounded = bool(knowledge)
    return _finalise(conv, answer, provider="fallback", grounded=grounded, sources=sources)


def _recent_history(conv, limit=6):
    msgs = list(conv.messages.order_by("-created_at")[:limit])
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs if m.role in ("user", "assistant")]


def _finalise(conv, answer, provider, grounded, sources):
    msg = AssistantMessage.objects.create(
        conversation=conv, role="assistant", content=answer,
        provider=provider, grounded=grounded, used_sources=sources,
    )
    conv.save(update_fields=[]) if False else None
    return {
        "answer": answer,
        "grounded": grounded,
        "provider": provider,
        "message_id": msg.id,
        "can_contact_support": not grounded,
    }
