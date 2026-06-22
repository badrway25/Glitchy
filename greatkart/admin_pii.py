"""Reusable masked admin columns (display-only PII redaction for list views)."""
from django.contrib import admin

from .pii import mask_email, mask_phone, mask_token


def masked_email_column(field, label="Email"):
    @admin.display(description=label)
    def _col(self, obj):
        return mask_email(getattr(obj, field, "") or "")
    _col.__name__ = "masked_" + field.replace("__", "_")
    return _col


def masked_user_email_column(field, label="Customer"):
    """For a FK to the user/account model — masks the related .email."""
    @admin.display(description=label)
    def _col(self, obj):
        rel = getattr(obj, field, None)
        return mask_email(getattr(rel, "email", "")) if rel else "—"
    _col.__name__ = "masked_user_" + field.replace("__", "_")
    return _col


def masked_phone_column(field, label="Phone"):
    @admin.display(description=label)
    def _col(self, obj):
        return mask_phone(getattr(obj, field, "") or "")
    _col.__name__ = "masked_" + field.replace("__", "_")
    return _col


def masked_token_column(field, label="Ref"):
    @admin.display(description=label)
    def _col(self, obj):
        return mask_token(getattr(obj, field, "") or "")
    _col.__name__ = "masked_" + field.replace("__", "_")
    return _col
