from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Order

# Single source of truth for the shippable countries, so the checkout <select> and
# the form's accepted values can never drift apart (previously the form accepted only
# 10 while the dropdown offered 14 — PT/IE/CA/AU silently failed validation).
from shipping.constants import COUNTRIES as COUNTRY_CHOICES

class OrderForm(forms.ModelForm):
    country = forms.ChoiceField(choices=COUNTRY_CHOICES)
    postal_code = forms.CharField(max_length=20, required=True)
    # Optional dial prefix from the premium prefix dropdown (e.g. "+39"); combined with the
    # national number and validated server-side below. The stored value is E.164.
    phone_prefix = forms.CharField(max_length=6, required=False)

    class Meta:
        model = Order
        fields = ['first_name', 'last_name', 'phone', 'email', 'address_line_1', 'address_line_2', 'country','postal_code', 'state', 'city', 'order_note']

    def clean(self):
        """International phone validation (server-side, phonenumbers) + light address hygiene.

        The frontend prefix dropdown is a UX aid only — this is the authoritative check.
        Rules: digits/spaces/()-. only; combined with the selected prefix (or parsed with the
        destination-country region when already international); must be a POSSIBLE number for
        that region; stored normalized as E.164. Never blocks legitimate international formats.
        """
        cleaned = super().clean()
        raw = (cleaned.get("phone") or "").strip()
        prefix = (cleaned.get("phone_prefix") or "").strip()
        country = (cleaned.get("country") or "").strip().upper()

        if raw:
            allowed = set("0123456789 +().-")
            if any(ch not in allowed for ch in raw):
                self.add_error("phone", _("Phone numbers can only contain digits, spaces and + ( ) - ."))
            else:
                import phonenumbers
                candidate = raw if raw.startswith("+") else ((prefix + raw) if prefix.startswith("+") else raw)
                try:
                    parsed = phonenumbers.parse(candidate, country or None)
                    if not phonenumbers.is_possible_number(parsed):
                        self.add_error("phone", _("This phone number looks too short or too long."))
                    elif not phonenumbers.is_valid_number(parsed):
                        self.add_error("phone", _("Please enter a valid phone number."))
                    else:
                        cleaned["phone"] = phonenumbers.format_number(
                            parsed, phonenumbers.PhoneNumberFormat.E164)
                except phonenumbers.NumberParseException:
                    self.add_error("phone", _("Please enter a valid phone number (e.g. +39 333 1234567)."))

        # Light address hygiene: normalize whitespace, reject control chars.
        for f in ("address_line_1", "address_line_2", "city", "state", "postal_code"):
            v = cleaned.get(f)
            if v:
                v = " ".join(str(v).split())
                if any(ord(ch) < 32 for ch in v):
                    self.add_error(f, _("This field contains invalid characters."))
                cleaned[f] = v
        return cleaned


class CheckoutForm(forms.Form):
    first_name = forms.CharField(max_length=50)
    last_name  = forms.CharField(max_length=50)
    email      = forms.EmailField()
    phone      = forms.CharField(max_length=20)

    address_line_1 = forms.CharField(max_length=100)
    address_line_2 = forms.CharField(max_length=100, required=False)

    city    = forms.CharField(max_length=50)
    state   = forms.CharField(max_length=50)
    country = forms.CharField(max_length=50)
    postal_code = forms.CharField(max_length=50)

    order_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    save_address = forms.BooleanField(required=False)  # ✅ checkbox