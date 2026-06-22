"""P0.1: PayPal finalization must be server-verified (fail-closed)."""
import json
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from orders.models import Order
from carts.models import Cart, CartItem
from store.models import Product
from category.models import Category


def _pending_guest_order(client):
    cat, _ = Category.objects.get_or_create(category_name="T", slug="t")
    p = Product.objects.create(product_name="P", slug="p", price=20, category=cat, stock=5, is_available=True)
    s = client.session; s.save()
    cart = Cart.objects.create(cart_id=s.session_key)
    CartItem.objects.create(cart=cart, product=p, quantity=1, is_active=True)
    o = Order.objects.create(first_name="G", last_name="G", phone="1", email="g@x.com",
                             address_line_1="x", city="c", state="s", country="IT",
                             order_total=20, tax=0, ip="127.0.0.1", order_number="PPTEST1",
                             is_ordered=False, is_guest=True, session_key=s.session_key, currency="EUR")
    return o


@override_settings(PAYPAL_ENABLED=False)
class PayPalDisabledTests(TestCase):
    def setUp(self):
        self.c = Client(enforce_csrf_checks=False)
        self.o = _pending_guest_order(self.c)

    def test_fake_completed_post_does_not_finalize(self):
        # The classic bypass: forge status=COMPLETED with a fake transID.
        r = self.c.post(reverse("payments"),
                        data=json.dumps({"orderID": "PPTEST1", "transID": "FAKE123",
                                         "status": "COMPLETED", "payment_method": "PayPal"}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 503)              # PayPal unavailable
        self.o.refresh_from_db()
        self.assertFalse(self.o.is_ordered)               # NOT finalized
        self.assertFalse(self.o.orderproduct_set.exists())

    def test_no_500(self):
        r = self.c.post(reverse("payments"),
                        data=json.dumps({"orderID": "PPTEST1", "transID": "x",
                                         "status": "COMPLETED", "payment_method": "PayPal"}),
                        content_type="application/json")
        self.assertNotEqual(r.status_code, 500)


@override_settings(PAYPAL_ENABLED=True)   # forced on, but verify_capture still fails-closed (no creds)
class PayPalEnabledButUnverifiedTests(TestCase):
    def setUp(self):
        self.c = Client(enforce_csrf_checks=False)
        self.o = _pending_guest_order(self.c)

    def test_unverified_capture_rejected(self):
        # paypal_available() requires client_id+secret; without them verify_capture -> False.
        r = self.c.post(reverse("payments"),
                        data=json.dumps({"orderID": "PPTEST1", "transID": "FAKE",
                                         "status": "COMPLETED", "payment_method": "PayPal"}),
                        content_type="application/json")
        self.assertIn(r.status_code, (402, 503))          # never finalizes on unverified
        self.o.refresh_from_db()
        self.assertFalse(self.o.is_ordered)
