"""Add-to-cart variant snapshot + enriched AJAX JSON (this phase).

The add flow must capture the colour-matched gallery image on the cart line,
echo it in the AJAX payload (which feeds the premium modal), keep the no-JS
redirect behaviour intact, and hand the snapshot over to the OrderProduct at
payment finalization.
"""
from django.test import TestCase
from django.urls import reverse

from carts.models import Cart, CartItem
from category.models import Category
from orders.models import Order, Payment
from orders.services import finalize_order_payment
from store.models import Product, ProductColorImage, ProductImage, Variation

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _make_product():
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    p = Product.objects.create(product_name="Snap Tee", slug="snap-tee",
                               price=25, stock=10, category=cat, is_available=True)
    img_b = ProductImage.objects.create(product=p, printify_src="https://img.example/black.jpg",
                                        sort_order=0)
    img_w = ProductImage.objects.create(product=p, printify_src="https://img.example/white.jpg",
                                        sort_order=1)
    for value in ("Black", "White"):
        Variation.objects.create(product=p, variation_category="color",
                                 variation_value=value, is_active=True)
    Variation.objects.create(product=p, variation_category="size",
                             variation_value="M", is_active=True)
    ProductColorImage.objects.create(product=p, color_value="black",
                                     image_ids=str(img_b.id), primary_image=img_b)
    ProductColorImage.objects.create(product=p, color_value="white",
                                     image_ids=str(img_w.id), primary_image=img_w)
    return p, img_b, img_w


class AddToCartSnapshotTests(TestCase):
    def setUp(self):
        self.product, self.img_b, self.img_w = _make_product()
        self.url = reverse("add_cart", args=[self.product.id])

    def _add(self, color, size="M", ajax=True):
        extra = AJAX if ajax else {}
        return self.client.post(self.url, {"color": color, "size": size}, **extra)

    def test_black_add_snapshots_black_image(self):
        resp = self._add("Black")
        self.assertEqual(resp.status_code, 200)
        item = CartItem.objects.get()
        self.assertEqual(item.selected_image_id, self.img_b.id)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["line"]["color"], "Black")
        self.assertEqual(data["line"]["size"], "M")
        self.assertEqual(data["line"]["image_url"], "https://img.example/black.jpg")
        self.assertEqual(data["line"]["thumb_url"], "https://img.example/black.jpg")
        self.assertEqual(data["line"]["quantity"], 1)
        self.assertEqual(data["line"]["product_name"], "Snap Tee")
        self.assertEqual(data["cart_url"], reverse("cart"))

    def test_white_add_snapshots_white_image(self):
        self._add("White")
        item = CartItem.objects.get()
        self.assertEqual(item.selected_image_id, self.img_w.id)

    def test_two_colors_two_lines_two_snapshots(self):
        self._add("Black")
        self._add("White")
        snaps = {ci.line_color_value(): ci.selected_image_id
                 for ci in CartItem.objects.all()}
        self.assertEqual(snaps, {"Black": self.img_b.id, "White": self.img_w.id})

    def test_repeat_add_increments_and_keeps_snapshot(self):
        self._add("Black")
        resp = self._add("Black")
        self.assertEqual(CartItem.objects.count(), 1)
        item = CartItem.objects.get()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.selected_image_id, self.img_b.id)
        self.assertEqual(resp.json()["line"]["quantity"], 2)

    def test_unmapped_color_falls_back_without_error(self):
        Variation.objects.create(product=self.product, variation_category="color",
                                 variation_value="Red", is_active=True)
        resp = self._add("Red")
        self.assertEqual(resp.status_code, 200)
        item = CartItem.objects.get()
        self.assertIsNone(item.selected_image)
        # fallback: first gallery image via display_url (no main image file)
        self.assertEqual(resp.json()["line"]["image_url"], "https://img.example/black.jpg")

    def test_no_js_post_still_redirects_to_cart(self):
        resp = self._add("Black", ajax=False)
        self.assertRedirects(resp, reverse("cart"))
        self.assertEqual(CartItem.objects.get().selected_image_id, self.img_b.id)

    def test_missing_options_contract_unchanged(self):
        resp = self.client.post(self.url, {}, **AJAX)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"ok": False, "needs_options": True})
        self.assertEqual(CartItem.objects.count(), 0)


class FinalizeSnapshotTests(TestCase):
    def _pending_order_with_cart(self, snapshot=True):
        product, img_b, _ = _make_product()
        s = self.client.session
        s.save()
        cart = Cart.objects.create(cart_id=s.session_key)
        item = CartItem.objects.create(cart=cart, product=product, quantity=1,
                                       is_active=True)
        item.variations.add(Variation.objects.get(product=product,
                                                  variation_value="Black"))
        if snapshot:
            item.selected_image = img_b
            item.save()
        order = Order.objects.create(
            first_name="G", last_name="G", phone="1", email="g@x.com",
            address_line_1="x", city="c", state="s", country="IT",
            order_total=25, tax=0, ip="127.0.0.1", order_number="SNAP-1",
            is_ordered=False, is_guest=True, session_key=s.session_key,
            currency="EUR")
        return order, img_b

    def _finalize(self, order):
        payment = Payment.objects.create(payment_id="pay-1", payment_method="Stripe",
                                         amount_paid="25", status="COMPLETED")
        finalize_order_payment(order=order, payment=payment)

    def test_snapshot_copied_to_order_product(self):
        order, img_b = self._pending_order_with_cart(snapshot=True)
        self._finalize(order)
        op = order.orderproduct_set.get()
        self.assertEqual(op.selected_image_id, img_b.id)
        self.assertEqual(op.line_image_url(), "https://img.example/black.jpg")
        self.assertEqual(CartItem.objects.count(), 0)   # cart cleared

    def test_missing_snapshot_resolved_at_finalize(self):
        order, img_b = self._pending_order_with_cart(snapshot=False)
        self._finalize(order)
        op = order.orderproduct_set.get()
        self.assertEqual(op.selected_image_id, img_b.id)


class ThumbnailSurfaceTests(TestCase):
    """Every line-thumbnail surface renders the COLOUR's image, not the hero."""

    def setUp(self):
        self.product, self.img_b, self.img_w = _make_product()
        self.client.post(reverse("add_cart", args=[self.product.id]),
                         {"color": "Black", "size": "M"})

    def test_cart_page_shows_black_thumb_with_color_alt(self):
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("https://img.example/black.jpg", html)
        self.assertNotIn("https://img.example/white.jpg", html)
        self.assertIn("Snap Tee — Black", html)

    def test_checkout_page_shows_black_thumb(self):
        html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn("https://img.example/black.jpg", html)
        self.assertNotIn("https://img.example/white.jpg", html)

    def test_second_line_white_shows_white_thumb(self):
        self.client.post(reverse("add_cart", args=[self.product.id]),
                         {"color": "White", "size": "M"})
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("https://img.example/black.jpg", html)
        self.assertIn("https://img.example/white.jpg", html)

    def test_quantity_change_keeps_thumb(self):
        self.client.post(reverse("add_cart", args=[self.product.id]),
                         {"color": "Black", "size": "M"})   # + stepper re-POST
        item = CartItem.objects.get()
        self.assertEqual(item.quantity, 2)
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("https://img.example/black.jpg", html)

    def test_order_complete_shows_snapshot_thumb(self):
        s = self.client.session
        s.save()
        order = Order.objects.create(
            first_name="G", last_name="G", phone="1", email="g@x.com",
            address_line_1="x", city="c", state="s", country="IT",
            order_total=25, tax=0, ip="127.0.0.1", order_number="SNAP-OC-1",
            is_ordered=False, is_guest=True, session_key=s.session_key,
            currency="EUR")
        payment = Payment.objects.create(payment_id="pay-oc", payment_method="Stripe",
                                         amount_paid="25", status="COMPLETED")
        finalize_order_payment(order=order, payment=payment)
        html = self.client.get(
            f"/orders/order_complete/?order_number={order.order_number}"
            f"&payment_id={payment.payment_id}").content.decode()
        self.assertIn("https://img.example/black.jpg", html)
        self.assertIn("oc-item-thumb", html)
