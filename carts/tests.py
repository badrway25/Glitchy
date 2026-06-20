from django.test import TestCase, override_settings
from django.urls import reverse

from category.models import Category
from orders.models import Order
from store.models import Product


@override_settings(SHIPPING_USE_PRINTIFY=False, STORE_TAX_RATE=2.0, SHIPPING_DEFAULT_COUNTRY="IT")
class GuestCheckoutTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(category_name="Tees", slug="tees")
        self.product = Product.objects.create(
            product_name="Basic Tee", slug="basic-tee", description="d", price=25,
            stock=10, is_available=True, category=self.cat,
            printify_product_id="pp1",
        )

    def test_guest_can_add_and_checkout(self):
        # Add to cart as anonymous user
        resp = self.client.get(reverse("add_cart", args=[self.product.id]), follow=True)
        self.assertEqual(resp.status_code, 200)

        # Guest checkout page renders (no login redirect)
        resp = self.client.get(reverse("checkout"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["is_guest"])

    def test_guest_place_order_creates_guest_order(self):
        self.client.get(reverse("add_cart", args=[self.product.id]))
        resp = self.client.post(reverse("place_order"), {
            "first_name": "Guest", "last_name": "User", "phone": "123456",
            "email": "guest@example.com", "address_line_1": "Via Test 1",
            "address_line_2": "", "country": "IT", "state": "RM",
            "postal_code": "00100", "city": "Rome", "order_note": "",
        })
        self.assertEqual(resp.status_code, 200)  # renders payments page
        order = Order.objects.get(email="guest@example.com")
        self.assertTrue(order.is_guest)
        self.assertIsNone(order.user_id)
        self.assertEqual(order.shipping_country, "IT")
        self.assertGreater(order.shipping_cost, 0)
        # grand total = subtotal(25) + shipping + 2% tax
        self.assertAlmostEqual(order.tax, 0.5, places=2)
        self.assertEqual(order.items_subtotal, 25.0)

    def test_empty_cart_checkout_redirects(self):
        resp = self.client.get(reverse("checkout"))
        self.assertEqual(resp.status_code, 302)
