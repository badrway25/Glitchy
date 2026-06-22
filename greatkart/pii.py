"""Central PII-masking helpers for admin lists, reports and logs.

These NEVER mutate stored data — they only redact what is *displayed*. The goal is to
keep admin list views usable for operators while minimising casual exposure of personal
data (GDPR data-minimisation). Detail views can still show full values to authorised staff.
"""


def _bullets(n):
    return "•" * max(1, min(n, 6))


def mask_email(email):
    """john.doe@example.com -> j•••@e•••.com"""
    email = (email or "").strip()
    if "@" not in email:
        return email[:1] + _bullets(3) if email else ""
    local, _, domain = email.partition("@")
    dparts = domain.rsplit(".", 1)
    dname = dparts[0]
    tld = ("." + dparts[1]) if len(dparts) == 2 else ""
    return f"{local[:1]}{_bullets(3)}@{dname[:1]}{_bullets(3)}{tld}"


def mask_phone(phone):
    """+391234567 -> •••••4567 (keep the last 4)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return ""
    return _bullets(5) + digits[-4:] if len(digits) > 4 else _bullets(len(digits))


def mask_name(first, last=""):
    """John Doe -> John D."""
    first = (first or "").strip()
    last = (last or "").strip()
    return (first + (f" {last[:1]}." if last else "")).strip()


def mask_address(*, city="", state="", country="", postal_code=""):
    """Show only coarse location — never the street line."""
    bits = [b for b in (city, state, postal_code, country) if b]
    return ", ".join(bits[:3]) if bits else "—"


def mask_tracking(tracking):
    """ABC123456789 -> ABC•••789 (enough to recognise, not to share)."""
    t = (tracking or "").strip()
    if len(t) <= 6:
        return _bullets(len(t)) if t else ""
    return f"{t[:3]}{_bullets(3)}{t[-3:]}"


def mask_token(value, keep=4):
    """Short prefix of a hash/session key, masked tail. For ip_hash / session_key."""
    v = (value or "").strip()
    if not v:
        return ""
    return f"{v[:keep]}{_bullets(3)}"


def mask_text(value, length=40):
    """Truncated preview of free text (support bodies, reviews) — no full dump in lists."""
    v = " ".join((value or "").split())
    return (v[:length] + "…") if len(v) > length else v
