"""Public assistant endpoints. CSRF-protected, rate-limited, input-capped.
Output is plain text (escaped client-side) — no HTML is ever returned."""
import json
import logging
import time

from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import AssistantFeedback, AssistantMessage

logger = logging.getLogger("assistant")

QUICK_QUESTIONS = [
    {"key": "find", "en": "Find a product",
     "it": "Trova un prodotto", "fr": "Trouver un produit"},
    {"key": "delivery", "en": "Delivery times & costs",
     "it": "Tempi e costi di consegna", "fr": "Délais et frais de livraison"},
    {"key": "payment", "en": "Payment problem",
     "it": "Problema con il pagamento", "fr": "Problème de paiement"},
    {"key": "order", "en": "Where is my order?",
     "it": "Dov'è il mio ordine?", "fr": "Où est ma commande ?"},
    {"key": "returns", "en": "How do returns work?",
     "it": "Come funzionano i resi?", "fr": "Comment fonctionnent les retours ?"},
]


def _lang(request):
    code = (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]
    return code if code in ("en", "it", "fr") else "en"


def _rate_limited(request):
    """Sliding 1-hour window per session. Returns True if over the limit."""
    limit = getattr(settings, "AI_RATE_LIMIT", 20)
    now = time.time()
    window = 3600
    hits = [t for t in request.session.get("assistant_hits", []) if now - t < window]
    if len(hits) >= limit:
        request.session["assistant_hits"] = hits
        return True
    hits.append(now)
    request.session["assistant_hits"] = hits
    return False


@require_GET
def suggestions(request):
    lang = _lang(request)
    enabled = getattr(settings, "AI_ASSISTANT_ENABLED", True)
    try:
        from .providers import OpenAIProvider
        ai_ready = OpenAIProvider().available()
    except Exception:
        ai_ready = False
    return JsonResponse({
        "enabled": bool(enabled),
        "ai_ready": bool(ai_ready),
        "questions": [{"key": q["key"], "text": q.get(lang, q["en"])} for q in QUICK_QUESTIONS],
        "greeting": {
            "en": "Hi! Ask me about shipping, returns, sizes, payments or our products.",
            "it": "Ciao! Chiedimi di spedizioni, resi, taglie, pagamenti o i nostri prodotti.",
            "fr": "Bonjour ! Posez-moi vos questions sur la livraison, les retours, les tailles, les paiements ou nos produits.",
        }[lang],
    })


@require_POST
def chat(request):
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return JsonResponse({"error": "disabled"}, status=503)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "bad_request"}, status=400)

    message = (payload.get("message") or "").strip()
    cap = getattr(settings, "AI_MAX_INPUT_CHARS", 600)
    if not message:
        return JsonResponse({"error": "empty"}, status=400)
    if len(message) > cap:
        message = message[:cap]

    if _rate_limited(request):
        return JsonResponse({
            "answer": _("You've reached the message limit for now. Please try again later "
                        "or contact our support team."),
            "rate_limited": True, "can_contact_support": True,
        }, status=429)

    try:
        result = services.answer_question(request, message)
    except Exception:  # never 500 the widget
        logger.exception("assistant chat failed")
        return JsonResponse({
            "answer": _("Sorry, something went wrong. Please try again or contact support."),
            "error": "internal", "can_contact_support": True,
        }, status=200)
    if getattr(request.user, "is_staff", False):
        # SAFE staff-only diagnostics: no key, no prompt, no PII — just enough to see
        # whether the store is really online and which sources grounded the answer.
        try:
            from .providers import OpenAIProvider
            from .models import AssistantConfig
            cfg = AssistantConfig.load()
            result["debug"] = {
                "assistant_mode": "online" if OpenAIProvider().available() else "limited",
                "provider_used": result.get("provider", ""),
                "openai_called": result.get("provider") == "openai",
                "config_enabled": bool(cfg and cfg.is_enabled),
                "language": result.get("language", ""),
            }
        except Exception:
            pass
    return JsonResponse(result)


@require_POST
def feedback(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    msg_id = payload.get("message_id")
    helpful = payload.get("helpful")
    if msg_id is None or helpful is None:
        return JsonResponse({"error": "bad_request"}, status=400)
    msg = AssistantMessage.objects.filter(id=msg_id, role="assistant").first()
    if not msg:
        return JsonResponse({"error": "not_found"}, status=404)
    AssistantFeedback.objects.create(message=msg, helpful=bool(helpful))
    return JsonResponse({"ok": True})


@require_POST
def support_handoff(request):
    """Create a support request (and dispatch to n8n) when the assistant can't help."""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    email = (payload.get("email") or "").strip()[:254]
    body = (payload.get("message") or "").strip()[:2000]
    if not email or not body:
        return JsonResponse({"error": "bad_request"}, status=400)
    if _rate_limited(request):
        return JsonResponse({"error": "rate_limited"}, status=429)

    try:
        from notifications.models import SupportMessage
        sm = SupportMessage.objects.create(
            from_email=email,
            subject="Assistant support request",
            body_text=body,
            language=_lang(request),
            account=request.user if request.user.is_authenticated else None,
        )
        # Best-effort n8n notification (never blocks / leaks).
        try:
            from notifications.dispatcher import dispatch_event
            from notifications import events as ev
            from notifications.email_settings import get_admin_notify_email
            dispatch_event(getattr(ev, "SUPPORT_INBOUND", "support.inbound"),
                           {"from_email": email, "subject": sm.subject,
                            "language": sm.language, "source": "assistant"},
                           recipient_email=get_admin_notify_email() or email)
        except Exception:
            logger.info("assistant support n8n dispatch skipped")
    except Exception:
        logger.exception("assistant support handoff failed")
        return JsonResponse({"error": "internal"}, status=200)
    return JsonResponse({"ok": True})
