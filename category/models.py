from django.db import models
from django.urls import reverse


class PublicCategoryManager(models.Manager):
    """Categories shown to customers (filters, nav, sitemap). Excludes technical
    categories such as a Printify import bucket (is_public=False)."""
    def get_queryset(self):
        return super().get_queryset().filter(is_public=True)


class Category(models.Model):
    category_name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(max_length=255, blank=True)
    cat_image = models.ImageField(upload_to='photos/categories', blank=True)
    # Customer-facing visibility. Technical/import buckets (e.g. a stray "Printify"
    # category) are set to False so they never reach filters, nav, breadcrumbs or sitemap.
    is_public = models.BooleanField(
        default=True,
        help_text="Show in customer filters / nav / sitemap. Uncheck for technical categories.")

    objects = models.Manager()          # all categories (admin / back-office)
    public = PublicCategoryManager()    # customer-facing only

    class Meta:
        verbose_name = 'category'
        verbose_name_plural = 'categories'

    def get_url(self):
            return reverse('products_by_category', args=[self.slug])

    def __str__(self):
        return self.category_name