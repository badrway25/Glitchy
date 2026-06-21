"""Storefront marketing/analytics models: a manageable announcement bar and a
lightweight first-party analytics event log (no third-party trackers)."""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Announcement(models.Model):
    """A dismissible top-of-page banner, managed in admin, multilingual."""

    message = models.CharField(max_length=160)
    message_it = models.CharField(max_length=160, blank=True, default="")
    message_fr = models.CharField(max_length=160, blank=True, default="")

    link_url = models.CharField(max_length=255, blank=True, default="",
                                help_text=_("Optional CTA link (relative or absolute)."))
    link_label = models.CharField(max_length=40, blank=True, default="")
    link_label_it = models.CharField(max_length=40, blank=True, default="")
    link_label_fr = models.CharField(max_length=40, blank=True, default="")

    is_active = models.BooleanField(default=True)
    dismissible = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text=_("Higher wins when several are active."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "-created_at"]
        verbose_name = _("Announcement")
        verbose_name_plural = _("Announcements")

    def __str__(self):
        return self.message

    def message_for(self, lang):
        return {"it": self.message_it, "fr": self.message_fr}.get(lang) or self.message

    def label_for(self, lang):
        return {"it": self.link_label_it, "fr": self.link_label_fr}.get(lang) or self.link_label


class AnalyticsEvent(models.Model):
    """First-party, privacy-light event (no PII, hashed/opaque session)."""

    NAME_CHOICES = [
        ("product_view", "product_view"),
        ("add_to_cart", "add_to_cart"),
        ("begin_checkout", "begin_checkout"),
        ("assistant_open", "assistant_open"),
        ("assistant_question", "assistant_question"),
        ("search_no_results", "search_no_results"),
        ("size_guide_open", "size_guide_open"),
        ("wishlist_add", "wishlist_add"),
        ("wishlist_remove", "wishlist_remove"),
        ("coupon_apply", "coupon_apply"),
        ("coupon_fail", "coupon_fail"),
        ("cart_save_for_later", "cart_save_for_later"),
        ("review_submit", "review_submit"),
        ("search_query", "search_query"),
        ("support_order_help", "support_order_help"),
    ]

    name = models.CharField(max_length=32, db_index=True)
    path = models.CharField(max_length=255, blank=True, default="")
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Analytics event")
        verbose_name_plural = _("Analytics events")

    def __str__(self):
        return f"{self.name} @ {self.created_at:%Y-%m-%d %H:%M}"
