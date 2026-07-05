import re

from django import forms
from django.utils.translation import gettext_lazy as _

from shipping.constants import COUNTRIES
from .models import Account
from .models import Address

_PHONE_RE = re.compile(r"^[0-9+()\-.\s]{6,20}$")


class AddressForm(forms.ModelForm):
    # dial prefix from the flag dropdown (same component as checkout); combined into E.164
    phone_prefix = forms.CharField(max_length=6, required=False)

    # Country as a validated choice (curated ISO-3166 alpha-2 we actually serve),
    # consistent with the shipping estimator dropdown.
    country = forms.ChoiceField(
        choices=[("", _("Select country"))] + [(code, name) for code, name in COUNTRIES],
        label=_("Country"))

    class Meta:
        model = Address
        fields = [
            "first_name", "last_name", "email", "phone",
            "address_line_1", "address_line_2",
            "city", "state", "postal_code", "country",
            "is_default",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ids + data attributes the shared Google autocomplete controller expects
        # (address-autocomplete.js is instantiated on this form exactly like on checkout)
        attrs = {
            "address_line_1": {"id": "addressLine1", "role": "combobox", "aria-expanded": "false",
                                "aria-autocomplete": "list", "autocomplete": "off"},
            "city": {"id": "cityInput", "data-addr-context": "", "role": "combobox",
                     "aria-expanded": "false", "autocomplete": "off"},
            "state": {"id": "stateInput", "data-addr-context": "", "role": "combobox",
                      "aria-expanded": "false", "autocomplete": "off"},
            "postal_code": {"id": "postalCodeInput", "data-addr-context": "", "role": "combobox",
                            "aria-expanded": "false", "autocomplete": "off"},
            "country": {"id": "countryInput", "data-addr-context": ""},
            "phone": {"id": "phoneInput", "inputmode": "tel", "autocomplete": "tel-national"},
        }
        for name, extra in attrs.items():
            if name in self.fields:
                self.fields[name].widget.attrs.update(extra)

    def clean(self):
        cleaned = super().clean()
        from orders.forms import clean_international_phone
        raw = (cleaned.get("phone") or "").strip()
        if raw:
            e164, err = clean_international_phone(
                raw, cleaned.get("phone_prefix") or "", cleaned.get("country") or "")
            if err:
                self.add_error("phone", err)
            elif e164:
                cleaned["phone"] = e164
        return cleaned
        widgets = {
            "address_line_2": forms.TextInput(attrs={"placeholder": _("Optional")}),
        }

    def clean_city(self):
        city = (self.cleaned_data.get("city") or "").strip()
        if not city:
            raise forms.ValidationError(_("Please enter a city."))
        return city

    def clean_postal_code(self):
        # Model allows blank, but a destination needs a postal code for shipping.
        pc = (self.cleaned_data.get("postal_code") or "").strip()
        if not pc:
            raise forms.ValidationError(_("Please enter a postal code."))
        return pc

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and not _PHONE_RE.match(phone):
            raise forms.ValidationError(_("Please enter a valid phone number."))
        return phone


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Enter Password',
        'class': 'form-control',
    }))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Confirm Password'
    }))

    class Meta:
        model = Account
        fields = ['first_name', 'last_name', 'phone_number', 'email', 'password']

    def clean(self):
        cleaned_data = super(RegistrationForm, self).clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password != confirm_password:
            raise forms.ValidationError(
                "Password does not match!"
            )

    def __init__(self, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs['placeholder'] = 'Enter First Name'
        self.fields['last_name'].widget.attrs['placeholder'] = 'Enter last Name'
        self.fields['phone_number'].widget.attrs['placeholder'] = 'Enter Phone Number'
        self.fields['email'].widget.attrs['placeholder'] = 'Enter Email Address'
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form-control'