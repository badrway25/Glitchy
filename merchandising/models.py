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
    seo_title = models.CharField(max_length=160, blank=True, default="")
    products = models.ManyToManyField("store.Product", related_name="collections", blank=True)

    # Editorial intro (short "why this collection" paragraph), translatable
    editorial_intro = models.TextField(blank=True, default="")
    editorial_intro_it = models.TextField(blank=True, default="")
    editorial_intro_fr = models.TextField(blank=True, default="")

    MOOD_CHOICES = [
        ("minimal", "Minimal"), ("bold", "Bold"), ("everyday", "Everyday"),
        ("street", "Street"), ("soft", "Soft"), ("gift_ready", "Gift-ready"),
    ]
    SEASON_CHOICES = [
        ("new_season", "New season"), ("essentials", "Essentials"), ("gifts", "Gifts"),
        ("summer", "Summer"), ("winter", "Winter"),
    ]
    mood = models.CharField(max_length=20, choices=MOOD_CHOICES, blank=True, default="")
    season = models.CharField(max_length=20, choices=SEASON_CHOICES, blank=True, default="")

    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False, help_text="Show on the homepage.")
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    def editorial_intro_for(self, lang):
        return {"it": self.editorial_intro_it, "fr": self.editorial_intro_fr}.get(lang) \
            or self.editorial_intro

    def seo_title_for(self):
        return self.seo_title or self.name

    def price_range(self):
        """(min, max) of active product prices, or None — real data only."""
        prices = [float(p.price) for p in self.active_products() if p.price]
        return (min(prices), max(prices)) if prices else None

    def main_colors(self, limit=6):
        """Distinct colour variation values across the collection's products (real)."""
        from store.models import Variation
        vals = (Variation.objects.filter(product__in=self.active_products(),
                                          variation_category="color", is_active=True)
                .values_list("variation_value", flat=True).distinct())
        seen, out = set(), []
        for v in vals:
            k = (v or "").strip().lower()
            if k and k not in seen:
                seen.add(k); out.append(v.strip())
            if len(out) >= limit:
                break
        return out

    def related(self, limit=3):
        """Other active collections, preferring same mood/season — never self, real only."""
        qs = Collection.objects.filter(is_active=True).exclude(pk=self.pk)
        same = list(qs.filter(models.Q(mood=self.mood) & ~models.Q(mood="")) |
                    qs.filter(models.Q(season=self.season) & ~models.Q(season="")))
        ids = {c.pk for c in same}
        out = [c for c in same if c.active_products().exists()][:limit]
        if len(out) < limit:
            for c in qs.exclude(pk__in=ids):
                if c.active_products().exists():
                    out.append(c)
                if len(out) >= limit:
                    break
        return out[:limit]

    def completeness(self):
        """Admin-only 0–100 editorial completeness score with the missing items."""
        checks = [
            ("subtitle", bool(self.subtitle.strip()), 12),
            ("hero_or_image", bool(self.image or self.hero_title), 12),
            ("editorial_intro", bool(self.editorial_intro.strip()), 16),
            ("products", self.products.count() >= 2, 20),
            ("mood", bool(self.mood), 12),
            ("season", bool(self.season), 12),
            ("seo", bool(self.meta_description.strip()), 16),
        ]
        total = sum(w for _, _, w in checks)
        got = sum(w for _, ok, w in checks if ok)
        return {"score": round(100 * got / total) if total else 0,
                "missing": [k for k, ok, _ in checks if not ok]}


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
