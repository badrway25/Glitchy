"""Curated list of supported shipping destinations (ISO-3166 alpha-2)."""
from django.utils.translation import gettext_lazy as _

# Ordered list of (code, translatable name). Kept intentionally focused on the
# brand's core EU markets plus a few common international destinations.
COUNTRIES = [
    ("IT", _("Italy")),
    ("FR", _("France")),
    ("DE", _("Germany")),
    ("ES", _("Spain")),
    ("NL", _("Netherlands")),
    ("BE", _("Belgium")),
    ("AT", _("Austria")),
    ("PT", _("Portugal")),
    ("IE", _("Ireland")),
    ("CH", _("Switzerland")),
    ("GB", _("United Kingdom")),
    ("US", _("United States")),
    ("CA", _("Canada")),
    ("AU", _("Australia")),
]

COUNTRY_NAMES = {code: name for code, name in COUNTRIES}


def country_name(code: str) -> str:
    return str(COUNTRY_NAMES.get((code or "").upper(), code or ""))
