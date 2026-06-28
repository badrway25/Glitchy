import re

from django import forms
from django.utils.translation import gettext_lazy as _

from shipping.constants import COUNTRIES
from .models import Account
from .models import Address

_PHONE_RE = re.compile(r"^[0-9+()\-.\s]{6,20}$")


class AddressForm(forms.ModelForm):
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