from django import forms
from django.utils.translation import gettext_lazy as _


class ReturnRequestForm(forms.Form):
    email = forms.EmailField(
        required=False,
        label=_("Email on the order"),
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": _("you@example.com")}),
    )
    reason = forms.CharField(
        label=_("Reason for return"),
        widget=forms.Textarea(attrs={
            "class": "form-control", "rows": 4,
            "placeholder": _("Tell us why you'd like to return your order (optional)."),
        }),
        required=False,
        max_length=1000,
    )

    def __init__(self, *args, require_email=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_email = require_email
        if require_email:
            self.fields["email"].required = True

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if self.require_email and not email:
            raise forms.ValidationError(_("Please enter the email used for this order."))
        return email
