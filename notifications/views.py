from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import events as ev
from .dispatcher import dispatch_event
from .models import NewsletterSubscriber


@require_POST
def newsletter_subscribe(request):
    """Public newsletter opt-in. Records consent + triggers a welcome email."""
    email = (request.POST.get("email") or "").strip().lower()
    consent = request.POST.get("consent") in ("on", "true", "1", "yes", None)
    lang = translation.get_language() or "en"

    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if not email or "@" not in email:
        if is_ajax:
            return JsonResponse({"ok": False, "error": "invalid_email"}, status=400)
        messages.error(request, _("Please enter a valid email address."))
        return redirect(request.META.get("HTTP_REFERER", "home"))

    sub, created = NewsletterSubscriber.objects.get_or_create(
        email=email,
        defaults={"language": lang[:5], "consent": bool(consent), "source": "website"},
    )
    if not created and sub.unsubscribed:
        sub.unsubscribed = False
        sub.consent = True
        sub.save(update_fields=["unsubscribed", "consent"])

    if created:
        dispatch_event(
            ev.NEWSLETTER_SUBSCRIBED,
            {"email": email},
            recipient_email=email,
            language=lang,
        )

    if is_ajax:
        return JsonResponse({"ok": True, "created": created})
    messages.success(request, _("Thanks for subscribing! Check your inbox to confirm."))
    return redirect(request.META.get("HTTP_REFERER", "home"))
