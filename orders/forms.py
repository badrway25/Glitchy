from django import forms
from .models import Order

# Single source of truth for the shippable countries, so the checkout <select> and
# the form's accepted values can never drift apart (previously the form accepted only
# 10 while the dropdown offered 14 — PT/IE/CA/AU silently failed validation).
from shipping.constants import COUNTRIES as COUNTRY_CHOICES

class OrderForm(forms.ModelForm):
    country = forms.ChoiceField(choices=COUNTRY_CHOICES)
    postal_code = forms.CharField(max_length=20, required=True)
    class Meta:
        model = Order
        fields = ['first_name', 'last_name', 'phone', 'email', 'address_line_1', 'address_line_2', 'country','postal_code', 'state', 'city', 'order_note']


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