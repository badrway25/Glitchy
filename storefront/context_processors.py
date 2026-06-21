"""Expose the active announcement (localized) to every template."""
from .models import Announcement


def announcement(request):
    lang = (getattr(request, "LANGUAGE_CODE", "en") or "en")[:2]
    ann = Announcement.objects.filter(is_active=True).first()
    if not ann:
        return {"ANNOUNCEMENT": None}
    return {"ANNOUNCEMENT": {
        "id": ann.id,
        "message": ann.message_for(lang),
        "link_url": ann.link_url,
        "link_label": ann.label_for(lang),
        "dismissible": ann.dismissible,
    }}
