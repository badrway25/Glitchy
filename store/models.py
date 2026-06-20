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
    
