from django.db import models
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
    rating = models.FloatField()
    ip = models.CharField(max_length=20, blank=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
