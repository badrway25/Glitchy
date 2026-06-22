from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from category.models import Category
from django.urls import reverse
from accounts.models import Account
from django.db.models import Avg, Count

# Create your models here.




class Product(models.Model):
    product_name    = models.CharField(max_length=200, unique=True)
    slug            = models.SlugField(max_length=200, unique=True)
    description     = models.TextField(max_length=2000, blank=True)
    price           = models.IntegerField()
    compare_at_price = models.IntegerField(blank=True, null=True,
                                           help_text="Optional 'was' price for sale display")
    images = models.ImageField(upload_to='photos/products', blank=True, null=True)
    stock           = models.IntegerField()
    is_available    = models.BooleanField(default=True)
    category        = models.ForeignKey(Category, on_delete=models.CASCADE)
    created_date    = models.DateTimeField(auto_now_add=True)
    modified_date   = models.DateTimeField(auto_now=True)
    printify_product_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    printify_blueprint_id = models.IntegerField(blank=True, null=True, db_index=True)
    printify_provider_id = models.IntegerField(blank=True, null=True,
                                               help_text="Printify print provider id (for shipping/cost)")
    sku = models.CharField(max_length=64, unique=True, blank=True, null=True)

    # Printify sync state
    SYNC_NOT_SYNCED = "not_synced"
    SYNC_SYNCED = "synced"
    SYNC_UPDATED = "updated"
    SYNC_DRAFT = "draft"
    SYNC_ERROR = "error"
    PRINTIFY_SYNC_CHOICES = [
        (SYNC_NOT_SYNCED, "Not synced"),
        (SYNC_SYNCED, "Synced"),
        (SYNC_UPDATED, "Updated"),
        (SYNC_DRAFT, "Draft"),
        (SYNC_ERROR, "Sync error"),
    ]
    printify_sync_status = models.CharField(max_length=16, choices=PRINTIFY_SYNC_CHOICES,
                                            default=SYNC_NOT_SYNCED)
    printify_synced_at = models.DateTimeField(blank=True, null=True)
    printify_sync_error = models.TextField(blank=True, default="")

    # Printify catalogue metadata (safe, non-sensitive — for admin/data-quality only)
    printify_blueprint_title = models.CharField(max_length=160, blank=True, default="")
    printify_provider_name = models.CharField(max_length=120, blank=True, default="")
    printify_visible = models.BooleanField(default=True,
                                           help_text="Mirrors Printify product visibility")
    printify_tags = models.CharField(max_length=400, blank=True, default="")
    printify_options_summary = models.CharField(max_length=300, blank=True, default="",
                                                help_text="e.g. 'Sizes: S–XXL · Colours: 5'")

    # --- Premium product detail content (bulleted "More" sections) ---
    composition = models.TextField(blank=True, default="",
                                   help_text="Materials / composition, e.g. '100% organic cotton'")
    fit_notes = models.TextField(blank=True, default="", help_text="Fit & sizing notes")
    care_instructions = models.TextField(blank=True, default="", help_text="Washing / care guidance")

    # --- Merchandising badges ---
    is_bestseller = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)

    # --- Economics: production cost fallback (per unit) for margin tracking ---
    base_cost = models.FloatField(default=0.0,
                                  help_text="Default production cost per unit (Printify). "
                                            "Variant-level cost overrides this when available.")

    def get_url(self):
        return reverse('product_detail', args=[self.category.slug, self.slug])

    def __str__(self):
        return self.product_name

    def is_new_arrival(self, days=30):
        from django.utils import timezone
        if not self.created_date:
            return False
        return (timezone.now() - self.created_date).days <= days

    def data_quality(self):
        """Admin-only 0–100 completeness score with a per-check breakdown.
        Never shown to customers (it can reference internal coverage)."""
        checks = []

        def chk(key, ok, weight):
            checks.append({"key": key, "ok": bool(ok), "weight": weight})

        has_variants = self.variation_set.exists() if hasattr(self, "variation_set") else False
        variant_costs = False
        gallery_count = self.gallery.count() if hasattr(self, "gallery") else 0
        try:
            from store.models import Variation
            variant_costs = Variation.objects.filter(
                product=self, production_cost__gt=0).exists()
        except Exception:
            pass
        has_reviews = False
        try:
            has_reviews = self.reviews.filter(status=True).exists()
        except Exception:
            pass
        has_faq = False
        try:
            from store.models import ProductFAQ
            has_faq = ProductFAQ.for_product(self).exists()
        except Exception:
            pass

        chk("composition", self.composition.strip(), 12)
        chk("fit_or_care", self.fit_notes.strip() or self.care_instructions.strip(), 10)
        chk("gallery_multi", gallery_count >= 2, 12)
        chk("blueprint_provider", self.printify_blueprint_id and self.printify_provider_id, 12)
        chk("variant_costs", variant_costs or self.base_cost > 0, 14)
        chk("synced", self.printify_sync_status in (self.SYNC_SYNCED, self.SYNC_UPDATED), 8)
        chk("recent_sync", bool(self.printify_synced_at), 6)
        chk("faq", has_faq, 8)
        chk("reviews", has_reviews, 8)
        chk("seo", bool((self.description or "").strip()) and len((self.product_name or "")) > 3, 10)

        total_w = sum(c["weight"] for c in checks)
        got = sum(c["weight"] for c in checks if c["ok"])
        score = round(100 * got / total_w) if total_w else 0
        missing = [c["key"] for c in checks if not c["ok"]]
        return {"score": score, "missing": missing, "checks": checks}

    def data_quality_score(self):
        return self.data_quality()["score"]

    def cover_image(self):
        """Best available image: explicit cover, else first gallery image."""
        if self.images:
            return self.images.url
        first = self.gallery.first()
        if first and first.image:
            return first.image.url
        return ""

    def hover_image(self):
        """Second distinct image for the card hover effect (empty if only one)."""
        cover = self.cover_image()
        for g in self.gallery.all():
            if g.image and g.image.url and g.image.url != cover:
                return g.image.url
        return ""

    def on_sale(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    def averageReview(self):
        reviews = ReviewRating.objects.filter(product=self, status=True).aggregate(average=Avg('rating'))
        avg = 0
        if reviews['average'] is not None:
            avg = float(reviews['average'])
        return avg

    def countReview(self):
        reviews = ReviewRating.objects.filter(product=self, status=True).aggregate(count=Count('id'))
        count = 0
        if reviews['count'] is not None:
            count = int(reviews['count'])
        return count

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to='photos/products/gallery', blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "id"]

    def __str__(self):
        return f"{self.product.product_name} image"
    
class VariationManager(models.Manager):
    def colors(self):
        return super(VariationManager, self).filter(variation_category='color', is_active=True)

    def sizes(self):
        return super(VariationManager, self).filter(variation_category='size', is_active=True)

variation_category_choice = (
    ('color', 'color'),
    ('size', 'size'),
)

class Variation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variation_category = models.CharField(max_length=100, choices=variation_category_choice)
    variation_value     = models.CharField(max_length=100)
    is_active           = models.BooleanField(default=True)
    created_date        = models.DateTimeField(auto_now=True)
    printify_variant_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    # Per-variant production cost from Printify (used for accurate margins)
    production_cost = models.FloatField(default=0.0)


    objects = VariationManager()

    def __str__(self):
        return self.variation_value


class ReviewRating(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(Account, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100, blank=True)
    review = models.TextField(max_length=500, blank=True)
    rating = models.FloatField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    ip = models.CharField(max_length=20, blank=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Ratings are 1–5 at the database level, not just in the form UI.
            models.CheckConstraint(condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                                   name="review_rating_1_5"),
        ]

    def __str__(self):
        return self.subject
    


class ProductFAQ(models.Model):
    """A FAQ entry shown on product pages and used as assistant context. Can be
    attached to one product, a whole category, or be global (both blank)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="faqs")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="faqs")

    question = models.CharField(max_length=200)
    question_it = models.CharField(max_length=200, blank=True, default="")
    question_fr = models.CharField(max_length=200, blank=True, default="")
    answer = models.TextField()
    answer_it = models.TextField(blank=True, default="")
    answer_fr = models.TextField(blank=True, default="")

    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Product FAQ"
        verbose_name_plural = "Product FAQs"

    def __str__(self):
        scope = self.product.product_name if self.product_id else (
            self.category.category_name if self.category_id else "Global")
        return f"[{scope}] {self.question}"

    def question_for(self, lang):
        return {"it": self.question_it, "fr": self.question_fr}.get(lang) or self.question

    def answer_for(self, lang):
        return {"it": self.answer_it, "fr": self.answer_fr}.get(lang) or self.answer

    @classmethod
    def for_product(cls, product):
        """Active FAQs relevant to a product: product-specific + its category + global."""
        from django.db.models import Q
        return cls.objects.filter(is_active=True).filter(
            Q(product=product) | Q(category=product.category, product__isnull=True)
            | Q(product__isnull=True, category__isnull=True))


class GeneralFAQ(models.Model):
    """Site-wide FAQ shown on the dedicated /faq/ page, grouped by category and
    used as assistant context. Separate from product-specific ProductFAQ."""
    CATEGORY_CHOICES = [
        ("shipping", "Shipping & delivery"),
        ("returns", "Returns & refunds"),
        ("payments", "Payments & security"),
        ("orders", "Orders & tracking"),
        ("account", "Account & wishlist"),
        ("sizing", "Sizing & products"),
        ("coupons", "Coupons & offers"),
        ("support", "Support & assistant"),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="support")

    question = models.CharField(max_length=200)
    question_it = models.CharField(max_length=200, blank=True, default="")
    question_fr = models.CharField(max_length=200, blank=True, default="")
    answer = models.TextField()
    answer_it = models.TextField(blank=True, default="")
    answer_fr = models.TextField(blank=True, default="")

    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "order", "id"]
        verbose_name = "General FAQ"
        verbose_name_plural = "General FAQs"

    def __str__(self):
        return f"[{self.category}] {self.question}"

    def question_for(self, lang):
        return {"it": self.question_it, "fr": self.question_fr}.get(lang) or self.question

    def answer_for(self, lang):
        return {"it": self.answer_it, "fr": self.answer_fr}.get(lang) or self.answer
