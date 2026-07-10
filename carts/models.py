from django.db import models
from store.models import Product, Variation
from accounts.models import Account


# Create your models here.

class Cart(models.Model):
    cart_id = models.CharField(max_length=250, blank=True)
    date_added = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.cart_id


class CartItem(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE, null=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variations = models.ManyToManyField(Variation, blank=True)
    cart    = models.ForeignKey(Cart, on_delete=models.CASCADE, null=True)
    quantity = models.IntegerField()
    is_active = models.BooleanField(default=True)
    printify_variant_id = models.IntegerField(blank=True, null=True)
    # Snapshot of the gallery image matching the colour chosen at add-to-cart
    # time, so the cart keeps showing the right mockup even if the catalogue
    # gallery/mapping changes later. Resolution order lives in
    # store/variant_thumbnail.py (snapshot -> colour mapping -> product fallback).
    selected_image = models.ForeignKey('store.ProductImage', blank=True, null=True,
                                       on_delete=models.SET_NULL, related_name='+')

    def sub_total(self):
        return self.product.price * self.quantity

    def line_image_url(self):
        """Variant-aware thumbnail URL for this line ('' -> placeholder)."""
        from store.variant_thumbnail import resolve_cart_item_image
        return resolve_cart_item_image(self)

    def line_color_value(self):
        """Selected colour display value ('' when the line has no colour)."""
        for v in self.variations.all():
            if v.variation_category == "color":
                return v.variation_value
        return ""

    def __unicode__(self):
        return self.product