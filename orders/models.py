from django.db import models
from accounts.models import Account
from store.models import Product, Variation



class Payment(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField(blank=True, default="")
    payment_id = models.CharField(max_length=100)
    payment_method = models.CharField(max_length=100)
    amount_paid = models.CharField(max_length=100) # this is the total amount paid
    status = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.payment_id


class Order(models.Model):
    STATUS = (
        ('New', 'New'),
        ('Accepted', 'Accepted'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    )

    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, blank=True, null=True)
    order_number = models.CharField(max_length=20)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)  # fits E.164 (+15 digits) after intl validation
    # Address verification audit trail (professional Google address flow)
    google_place_id = models.CharField(max_length=128, blank=True, default="")
    address_verified = models.BooleanField(default=False)
    address_manual_confirmed = models.BooleanField(default=False)
    email = models.EmailField(max_length=100)
    address_line_1 = models.CharField(max_length=100)
    address_line_2 = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    city = models.CharField(max_length=50)
    postal_code = models.CharField(max_length=20, blank=True, default="")
    order_note = models.CharField(max_length=200, blank=True)

    # --- Customer-facing money (all in `currency`) ---
    currency = models.CharField(max_length=3, default="EUR")
    items_subtotal = models.FloatField(default=0.0)
    shipping_cost = models.FloatField(default=0.0)      # charged to customer
    discount = models.FloatField(default=0.0)           # coupon discount applied
    coupon_code = models.CharField(max_length=32, blank=True, default="")
    order_total = models.FloatField()                   # grand total (subtotal + tax + shipping − discount)
    tax = models.FloatField()

    # --- Our costs (for margin tracking) ---
    cost_production = models.FloatField(default=0.0)     # Printify production cost
    cost_shipping = models.FloatField(default=0.0)       # Printify shipping cost to us
    payment_fee = models.FloatField(default=0.0)         # Stripe / PSP fee
    refunded_amount = models.FloatField(default=0.0)

    # --- Shipping / locale ---
    shipping_country = models.CharField(max_length=2, blank=True, default="")
    shipping_min_days = models.PositiveIntegerField(default=0)
    shipping_max_days = models.PositiveIntegerField(default=0)
    language_code = models.CharField(max_length=5, default="en")

    # --- Guest checkout ---
    is_guest = models.BooleanField(default=False)
    session_key = models.CharField(max_length=64, blank=True, default="")

    status = models.CharField(max_length=10, choices=STATUS, default='New')
    ip = models.CharField(blank=True, max_length=40)
    is_ordered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Printify fulfilment ---
    printify_order_id = models.CharField(max_length=64, blank=True, null=True)
    printify_status = models.CharField(max_length=32, blank=True, null=True)
    printify_last_error = models.TextField(blank=True, null=True)
    tracking_number = models.CharField(max_length=128, blank=True, default="")
    tracking_url = models.URLField(blank=True, default="")
    carrier = models.CharField(max_length=64, blank=True, default="")
    fulfilled_at = models.DateTimeField(blank=True, null=True)

    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def full_address(self):
        return f'{self.address_line_1} {self.address_line_2}'

    def __str__(self):
        return self.order_number or self.first_name

    # ------------------------------------------------------------------ #
    # Margin helpers (delegate to the tested service in orders.margins)
    # ------------------------------------------------------------------ #
    def margins(self):
        from .margins import compute_margins
        return compute_margins(self)

    @property
    def net_margin(self):
        return self.margins().net_margin

    @property
    def margin_pct(self):
        return self.margins().margin_pct

    @property
    def margin_band(self):
        return self.margins().band


class OrderProduct(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, blank=True, null=True)
    user = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variations = models.ManyToManyField(Variation, blank=True)
    quantity = models.IntegerField()
    product_price = models.FloatField()
    production_cost = models.FloatField(default=0.0)   # snapshot at order time
    ordered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Image snapshot copied from the cart line at finalize time (or resolved
    # then) so historical orders keep showing the purchased colour's mockup.
    selected_image = models.ForeignKey('store.ProductImage', blank=True, null=True,
                                       on_delete=models.SET_NULL, related_name='+')

    def line_total(self):
        return float(self.product_price) * int(self.quantity)

    def line_image_url(self):
        """Variant-aware thumbnail URL for this order line ('' -> placeholder)."""
        from store.variant_thumbnail import resolve_order_item_image
        return resolve_order_item_image(self)

    def line_color_value(self):
        for v in self.variations.all():
            if v.variation_category == "color":
                return v.variation_value
        return ""

    def __str__(self):
        return self.product.product_name