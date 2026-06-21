"""First-party analytics beacon endpoint (no third-party trackers)."""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import AnalyticsEvent

ALLOWED = {n for n, _ in AnalyticsEvent.NAME_CHOICES}


@require_POST
def track_event(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False}, status=400)
    name = (payload.get("name") or "").strip()
    if name not in ALLOWED:
        return JsonResponse({"ok": False}, status=400)
    if not request.session.session_key:
        request.session.save()
    meta = payload.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    # keep meta small and free of anything sensitive
    meta = {str(k)[:40]: str(v)[:120] for k, v in list(meta.items())[:8]}
    AnalyticsEvent.objects.create(
        name=name,
        path=(payload.get("path") or request.META.get("HTTP_REFERER", ""))[:255],
        session_key=request.session.session_key or "",
        meta=meta,
    )
    return JsonResponse({"ok": True})
