"""The quote handed to the page must equal the numbers rendered on the page.

The discount used to be applied *outside* `compute_cart_totals` on the render path
and *inside* it on the AJAX path, so the canonical `checkout_quote` payload carried
an undiscounted grand total while the summary showed a discounted one. Nothing was
visibly broken, but any future hydration from that payload would have shown the
customer a total they would not be charged.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from carts.models import Cart, CartItem
from category.models import Category
from promotions.models import Coupon
from store.models import Product

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@override_settings(SHIPPING_USE_PRINTIFY=False, STORE_TAX_RATE=2.0,
                   SHIPPING_FREE_THRESHOLD=0,
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class DiscountConsistencyTests(TestCase):
    def setUp(self):
        cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
        product = Product.objects.create(
            product_name="Disc Tee", slug="disc-tee", price=50, stock=10,
            category=cat, is_available=True)
        session = self.client.session
        session.save()
        cart = Cart.objects.create(cart_id=session.session_key)
        CartItem.objects.create(product=product, cart=cart, quantity=1, is_active=True)

    def _apply_coupon(self):
        Coupon.objects.create(code="SAVE10", discount_type="fixed", value=Decimal("10"),
                              is_active=True)
        self.client.post(reverse("promotions:apply"), {"code": "SAVE10"})

    def test_rendered_total_equals_canonical_quote_without_coupon(self):
        page = self.client.get(reverse("checkout"))
        quote = page.context["checkout_quote"]
        self.assertEqual(round(float(page.context["grand_total"]), 2),
                         round(quote["grand_total"], 2))

    def test_rendered_total_equals_canonical_quote_with_coupon(self):
        self._apply_coupon()
        page = self.client.get(reverse("checkout"))
        quote = page.context["checkout_quote"]
        self.assertGreater(page.context["discount"], 0)
        self.assertEqual(round(float(page.context["grand_total"]), 2),
                         round(quote["grand_total"], 2))
        self.assertEqual(round(quote["discount"], 2),
                         round(float(page.context["discount"]), 2))

    def test_ajax_summary_matches_the_rendered_page(self):
        self._apply_coupon()
        page = self.client.get(reverse("checkout"))
        country = page.context["prefill"]["country"] or "IT"
        data = self.client.post(reverse("shipping_estimate"),
                                {"country": country, "postal_code": "20100"},
                                **AJAX).json()["summary"]
        self.assertEqual(round(float(page.context["grand_total"]), 2),
                         round(data["grand_total"], 2))
