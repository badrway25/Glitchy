"""Template helpers for building shareable filter URLs (chip removal, sort swap)."""
from django import template

register = template.Library()

# Safe color-name -> hex mapping for premium swatches. Unknown names fall back to
# a neutral tone (never an invented bright colour). Covers the catalogue's values.
_COLOR_HEX = {
    "black": "#1c1a17", "white": "#ffffff", "ivory": "#f3eee0", "cream": "#f3eee0",
    "grey": "#9aa0a6", "gray": "#9aa0a6", "silver": "#c9ccd1", "charcoal": "#36373a",
    "dark heather": "#6e6f72", "heather": "#b9bcc2", "heather grey": "#b9bcc2",
    "navy": "#1f2a44", "blue": "#2f5fa6", "blu": "#2f5fa6", "royal": "#2f5fa6",
    "light blue": "#9cc1e6", "teal": "#2f7d7d", "red": "#b23b3b", "maroon": "#5c2b2b",
    "burgundy": "#5c2b34", "green": "#3f7d52", "olive": "#6b7a3a", "forest": "#2f5d3a",
    "beige": "#d8c9a8", "sand": "#cbb892", "tan": "#c8a97e", "brown": "#6b4f3a",
    "pink": "#d98aa6", "rose": "#caa3ac", "purple": "#6b4e9a", "lilac": "#b6a3d6",
    "yellow": "#d9b44a", "mustard": "#c9962f", "orange": "#cf7a3a", "gold": "#a6824c",
}


@register.filter
def color_hex(value):
    """Best-effort hex for a colour name; neutral fallback for unknowns."""
    if not value:
        return "#cfc8bd"
    return _COLOR_HEX.get(str(value).strip().lower(), "#cfc8bd")


@register.filter
def is_light_color(value):
    """True for very light swatches that need a visible border (white/ivory/cream)."""
    return str(value).strip().lower() in {"white", "ivory", "cream", "silver", "beige", "sand"}


@register.simple_tag(takes_context=True)
def qs_remove(context, param, value=None):
    """Current querystring with one (param[, value]) removed. For multi-value params
    (color, size) only the given value is dropped; otherwise the whole param goes.
    Always drops `page`. Returns an encoded string WITHOUT a leading '?'."""
    request = context.get("request")
    if not request:
        return ""
    qd = request.GET.copy()
    qd.pop("page", None)
    if param in qd:
        if value is not None and param in ("color", "size"):
            remaining = [v for v in qd.getlist(param) if v != str(value)]
            qd.setlist(param, remaining)
            if not remaining:
                qd.pop(param, None)
        else:
            qd.pop(param, None)
    return qd.urlencode()


@register.simple_tag(takes_context=True)
def qs_set(context, **kwargs):
    """Current querystring with the given params set/overridden (drops `page`)."""
    request = context.get("request")
    if not request:
        return ""
    qd = request.GET.copy()
    qd.pop("page", None)
    for k, v in kwargs.items():
        if v in (None, ""):
            qd.pop(k, None)
        else:
            qd[k] = v
    return qd.urlencode()
