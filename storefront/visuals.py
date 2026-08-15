"""Named homepage image slots — designed artwork by default, admin-editable on demand.

The homepage ships with hand-picked static artwork whose crops, aspect ratios and
responsive sources are part of the design. Making those images editable must not
put that at risk, so this module works slot-by-slot:

* every slot declares its fallback static asset, recommended size, aspect ratio
  and default alt text — the guidance the admin form validates against;
* the storefront asks `visual_for(slot)` and gets a ready-to-render dict; with no
  (or an invalid/inactive) override it returns the original static asset, so the
  page is byte-for-byte what it was before;
* uploads are validated (dimensions, aspect ratio, file size, real raster format)
  BEFORE they can reach a page, so a wrong upload cannot break the layout.

Focal point (x/y percentages) maps to `object-position`, so an admin can re-centre
a crop instead of distorting it — images are never stretched.
"""
from __future__ import annotations

from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

#: Slot registry — the contract between the design and the admin.
SLOTS = {
    "home_hero": {
        "label": _("Home hero"),
        "help": _("Full-bleed editorial hero at the top of the homepage."),
        "fallback_static": "images/home/pexels/hero-editorial-1280.jpg",
        "fallback_static_mobile": "images/home/pexels/hero-editorial-mobile-900.jpg",
        "default_alt": _("Editorial fashion campaign — tailored black look on a "
                         "dramatic studio backdrop"),
        "recommended_width": 2000,
        "recommended_height": 900,
        "aspect_ratio": 2000 / 900,
        "min_width": 1200,
        "min_height": 540,
        "focal_default": (60, 28),
    },
    "home_edit_1": {
        "label": _("Edit card 1"),
        "help": _("First card of “The edit” trio."),
        "fallback_static": "images/home/pexels/edit-neutrals-760.jpg",
        "default_alt": _("Minimalist beige shirt on a hanger"),
        "recommended_width": 760,
        "recommended_height": 950,
        "aspect_ratio": 760 / 950,
        "min_width": 440,
        "min_height": 550,
        "focal_default": (50, 50),
    },
    "home_edit_2": {
        "label": _("Edit card 2"),
        "help": _("Second card of “The edit” trio."),
        "fallback_static": "images/home/pexels/edit-tees-760.jpg",
        "default_alt": _("Model wearing a clean white everyday t-shirt"),
        "recommended_width": 760,
        "recommended_height": 950,
        "aspect_ratio": 760 / 950,
        "min_width": 440,
        "min_height": 550,
        "focal_default": (50, 50),
    },
    "home_edit_3": {
        "label": _("Edit card 3"),
        "help": _("Third card of “The edit” trio."),
        "fallback_static": "images/home/pexels/edit-afterdark-760.jpg",
        "default_alt": _("Moody evening look in low light"),
        "recommended_width": 760,
        "recommended_height": 950,
        "aspect_ratio": 760 / 950,
        "min_width": 440,
        "min_height": 550,
        "focal_default": (50, 50),
    },
    "home_editorial": {
        "label": _("Editorial band"),
        "help": _("Wide craft/fabric image in the editorial split section."),
        "fallback_static": "images/home/pexels/editorial-fabric-1200.jpg",
        "fallback_static_mobile": "images/home/pexels/editorial-fabric-700.jpg",
        "default_alt": _("Close-up of premium soft cotton fabric, naturally draped"),
        "recommended_width": 1200,
        "recommended_height": 900,
        "aspect_ratio": 1200 / 900,
        "min_width": 700,
        "min_height": 520,
        "focal_default": (50, 50),
    },
}

#: how far an upload may drift from the slot's aspect ratio before we refuse it
ASPECT_TOLERANCE = 0.28
#: hard ceiling for an upload (bytes) — keeps the homepage fast
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")


def slot_choices():
    return [(key, cfg["label"]) for key, cfg in SLOTS.items()]


def slot_config(slot):
    return SLOTS.get(slot) or {}


def _static_or_empty(path):
    if not path:
        return ""
    try:
        return static(path)
    except Exception:
        return ""


def visual_for(slot):
    """Resolved image for a slot: the admin's override when valid, else the design's.

    Returns a dict the template can render directly:
    {url, mobile_url, alt, object_position, is_custom, width, height}.
    """
    cfg = slot_config(slot)
    fallback = {
        "url": _static_or_empty(cfg.get("fallback_static")),
        "mobile_url": _static_or_empty(cfg.get("fallback_static_mobile")),
        "alt": cfg.get("default_alt", ""),
        "object_position": "%s%% %s%%" % cfg.get("focal_default", (50, 50)),
        "is_custom": False,
        "width": cfg.get("recommended_width", 0),
        "height": cfg.get("recommended_height", 0),
    }
    if not cfg:
        return fallback

    try:
        from .models import SiteVisualAsset
        asset = (SiteVisualAsset.objects
                 .filter(slot=slot, is_active=True)
                 .exclude(image="")
                 .order_by("-updated_at").first())
    except Exception:          # never let a CMS lookup take the homepage down
        return fallback
    if asset is None:
        return fallback

    try:
        url = asset.image.url
    except Exception:
        return fallback
    if not url:
        return fallback

    mobile_url = ""
    if asset.mobile_image:
        try:
            mobile_url = asset.mobile_image.url
        except Exception:
            mobile_url = ""

    return {
        "url": url,
        "mobile_url": mobile_url or fallback["mobile_url"],
        "alt": asset.alt_text or cfg.get("default_alt", ""),
        "object_position": "%d%% %d%%" % (asset.focal_point_x, asset.focal_point_y),
        "is_custom": True,
        "width": asset.width or cfg.get("recommended_width", 0),
        "height": asset.height or cfg.get("recommended_height", 0),
    }


def all_visuals():
    """Every slot resolved once — what the homepage context needs."""
    return {slot: visual_for(slot) for slot in SLOTS}
