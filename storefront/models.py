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
        ("autocomplete_select", "autocomplete_select"),
        ("support_order_help", "support_order_help"),
        ("recommendation_view", "recommendation_view"),
        ("recommendation_click", "recommendation_click"),
        ("outfit_view", "outfit_view"),
        ("outfit_add_to_cart", "outfit_add_to_cart"),
        ("style_quiz_start", "style_quiz_start"),
        ("style_quiz_complete", "style_quiz_complete"),
        ("filter_apply", "filter_apply"),
        ("filter_clear", "filter_clear"),
        ("filter_no_results", "filter_no_results"),
        ("search_with_filters", "search_with_filters"),
        ("collection_view", "collection_view"),
        ("notification_signup", "notification_signup"),
        ("high_intent_user", "high_intent_user"),
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


class SiteVisualAsset(models.Model):
    """An admin-managed override for one named homepage image slot.

    The site ships with designed static artwork (see storefront/visuals.py); a row
    here replaces one slot with an upload. Rows are validated on the way in
    (dimensions, aspect ratio, weight, real raster format) so a well-meaning upload
    cannot break the layout, and anything missing or inactive silently falls back
    to the original static asset."""

    slot = models.CharField(max_length=40, unique=True, db_index=True,
                            help_text=_("Which homepage image this replaces."))
    title = models.CharField(max_length=120, blank=True, default="",
                             help_text=_("Internal label — never shown to customers."))
    image = models.ImageField(upload_to="site_visuals/", blank=True, null=True)
    mobile_image = models.ImageField(upload_to="site_visuals/", blank=True, null=True,
                                     help_text=_("Optional portrait crop for phones."))
    alt_text = models.CharField(max_length=200, blank=True, default="",
                                help_text=_("Describes the image for screen readers "
                                            "and SEO. Required when uploading."))
    focal_point_x = models.PositiveSmallIntegerField(
        default=50, help_text=_("Horizontal focus %, 0 = left, 100 = right."))
    focal_point_y = models.PositiveSmallIntegerField(
        default=50, help_text=_("Vertical focus %, 0 = top, 100 = bottom."))
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(
        default=True, help_text=_("Uncheck to instantly restore the original image."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ["slot"]
        verbose_name = _("Site visual")
        verbose_name_plural = _("Site visuals")

    def __str__(self):
        from .visuals import slot_config
        return str(slot_config(self.slot).get("label") or self.slot)

    def save(self, *args, **kwargs):
        # cache the real pixel size so templates can reserve space (no layout shift)
        if self.image:
            try:
                self.width, self.height = self.image.width, self.image.height
            except Exception:
                self.width = self.height = 0
        super().save(*args, **kwargs)

    @property
    def is_custom(self) -> bool:
        return bool(self.is_active and self.image)
