"""Template helpers for building shareable filter URLs (chip removal, sort swap)."""
from django import template

register = template.Library()


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
