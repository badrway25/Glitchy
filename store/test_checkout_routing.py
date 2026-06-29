"""Phase 60: checkout routing — the real checkout is /cart/checkout/.

A bare /checkout/ must not 404 (it redirects to the real checkout), the named
'checkout' URL resolves under /cart/, and an empty-cart checkout degrades to /store/.
"""
from django.test import TestCase
from django.urls import reverse


class CheckoutRoutingTests(TestCase):
    def test_named_checkout_is_under_cart(self):
        self.assertEqual(reverse("checkout"), "/cart/checkout/")

    def test_bare_checkout_redirects_not_404(self):
        # /checkout/ used to 404; now it 302s to the real checkout.
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")

    def test_bare_checkout_localized_redirect(self):
        r = self.client.get("/it/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/it/cart/checkout/")

    def test_empty_cart_checkout_redirects_to_store(self):
        # No cart contents -> checkout sends the user to the store (nothing to buy).
        r = self.client.get("/cart/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/store/", r.headers["Location"])
