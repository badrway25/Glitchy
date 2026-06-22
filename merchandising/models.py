"""Merchandising & personalization: curated relations, collections, outfits and
back-in-stock / drop notification sign-ups. All customer-facing text is EN/IT/FR."""
from django.conf import settings
from django.db import models
from django.utils.text import slugify


class ProductRelation(models.Model):
    """A curated relationship between two real products (admin-managed)."""
    RELATED = "related"
    COMPLETE_LOOK = "complete_look"
    ALTERNATIVE = "alternative"
    BEST_MATCH = "best_match"
    TYPE_CHOICES = [
        (RELATED, "Related"), (COMPLETE_LOOK, "Complete the look"),
        (ALTERNATIVE, "Alternative"), (BEST_MATCH, "Best match"),
    ]
    from_product = models.ForeignKey("store.Product", on_delete=models.CASCADE,
                                     related_name="relations_from")
    to_product = models.ForeignKey("store.Product", on_delete=models.CASCADE,
                                   related_name="relations_to")
    relation_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=RELATED)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["from_product", "to_product", "relation_type"],
                                    name="uniq_product_relation"),
            models.CheckConstraint(condition=~models.Q(from_product=models.F("to_product")),
                                   name="relation_not_self"),
        ]

    def __str__(self):
        return f"{self.from_product_id}→{self.to_product_id} ({self.relation_type})"


class Collection(models.Model):
    """A merchandising landing page grouping real products (e.g. New Season)."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    subtitle = models.CharField(max_length=200, blank=True, default="")
    subtitle_it = models.CharField(max_length=200, blank=True, default="")
    subtitle_fr = models.CharField(max_length=200, blank=True, default="")
    hero_title = models.CharField(max_length=160, blank=True, default="")
    hero_title_it = models.CharField(max_length=160, blank=True, default="")
    hero_title_fr = models.CharField(max_length=160, blank=True, default="")
    image = models.URLField(blank=True, default="")
    meta_description = models.CharField(max_length=200, blank=True, default="")
    products = models.ManyToManyField("store.Product", related_name="collections", blank=True)

    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False, help_text="Show on the homepage.")
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_url(self):
        from django.urls import reverse
        return reverse("merchandising:collection", args=[self.slug])

    def hero_title_for(self, lang):
        return {"it": self.hero_title_it, "fr": self.hero_title_fr}.get(lang) or self.hero_title or self.name

    def subtitle_for(self, lang):
        return {"it": self.subtitle_it, "fr": self.subtitle_fr}.get(lang) or self.subtitle

    def active_products(self):
        return self.products.filter(is_available=True)


class Outfit(models.Model):
    """A 'Complete the look' editorial outfit grouping real products."""
    title = models.CharField(max_length=140)
    title_it = models.CharField(max_length=140, blank=True, default="")
    title_fr = models.CharField(max_length=140, blank=True, default="")
    description = models.CharField(max_length=300, blank=True, default="")
    description_it = models.CharField(max_length=300, blank=True, default="")
    description_fr = models.CharField(max_length=300, blank=True, default="")
    image = models.URLField(blank=True, default="")
    products = models.ManyToManyField("store.Product", related_name="outfits", blank=True)
    # An outfit can be anchored to a product so it shows on that PDP.
    anchor_product = models.ForeignKey("store.Product", on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="anchored_outfits")
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def title_for(self, lang):
        return {"it": self.title_it, "fr": self.title_fr}.get(lang) or self.title

    def description_for(self, lang):
        return {"it": self.description_it, "fr": self.description_fr}.get(lang) or self.description

    def active_products(self):
        return self.products.filter(is_available=True)


class ProductNotificationSignup(models.Model):
    """'Notify me' — back-in-stock / new-drop interest. No availability is promised."""
    BACK_IN_STOCK = "back_in_stock"
    NEW_DROP = "new_drop"
    TYPE_CHOICES = [(BACK_IN_STOCK, "Back in stock"), (NEW_DROP, "New drop")]

    email = models.EmailField()
    product = models.ForeignKey("store.Product", on_delete=models.CASCADE,
                                null=True, blank=True, related_name="notification_signups")
    variant = models.CharField(max_length=80, blank=True, default="")
    notify_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=BACK_IN_STOCK)
    consent = models.BooleanField(default=False)
    ip_hash = models.CharField(max_length=64, blank=True, default="")
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} · {self.notify_type}"
