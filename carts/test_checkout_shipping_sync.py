"""The Order summary and the delivery estimate must never disagree.

Regression suite for the reported bug: "Estimate delivery updates the shipping
when I change country, but Order summary keeps a static/wrong value." The real
defect was deeper — two independent engines priced shipping (settings rate table
for the summary/order, Printify profiles for the widget), so the two blocks
disagreed even on the same country and after a full reload.
"""
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from carts.models import Cart, CartItem
from category.models import Category
from store.models import Product

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _seed_cart(client, price=25, qty=1, express=False):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    product = Product.objects.create(
        product_name="Sync Tee", slug="sync-tee", price=price, stock=10,
        category=cat, is_available=True, printify_express_eligible=express,
        printify_express_enabled=express)
    session = client.session
    session.save()
    cart = Cart.objects.create(cart_id=session.session_key)
    CartItem.objects.create(product=product, cart=cart, quantity=qty, is_active=True)
    return product


@override_settings(SHIPPING_USE_PRINTIFY=False, STORE_TAX_RATE=2.0,
                   SHIPPING_FREE_THRESHOLD=0,
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class SummaryEstimateAgreementTests(TestCase):
    def setUp(self):
        _seed_cart(self.client)

    def _estimate(self, country, **extra):
        payload = {"country": country, "postal_code": "20100"}
        payload.update(extra)
        return self.client.post(reverse("shipping_estimate"), payload, **AJAX)

    def test_endpoint_returns_a_full_summary(self):
        data = self._estimate("IT").json()
        self.assertIn("summary", data)
        summary = data["summary"]
        for key in ("items_subtotal", "shipping_cost", "tax", "grand_total",
                    "shipping_display", "grand_total_display", "method"):
            self.assertIn(key, summary)

    def test_estimate_shipping_equals_summary_shipping(self):
        """The number in the widget IS the number in the summary."""
        data = self._estimate("IT").json()
        self.assertEqual(round(data["shipping_cost"], 2),
                         round(data["summary"]["shipping_cost"], 2))

    def test_estimate_matches_what_the_checkout_page_renders(self):
        page = self.client.get(reverse("checkout"))
        rendered = page.context["shipping_cost"]
        data = self._estimate(page.context["prefill"]["country"] or "IT").json()
        self.assertEqual(round(float(rendered), 2),
                         round(data["summary"]["shipping_cost"], 2))

    def test_country_change_moves_both_shipping_and_grand_total(self):
        it = self._estimate("IT").json()["summary"]
        us = self._estimate("US").json()["summary"]
        self.assertNotEqual(it["shipping_cost"], us["shipping_cost"])
        self.assertNotEqual(it["grand_total"], us["grand_total"])

    def test_summary_totals_are_internally_consistent(self):
        s = self._estimate("US").json()["summary"]
        expected = round(s["items_subtotal"] + s["tax"] + s["shipping_cost"]
                         - s["discount"], 2)
        self.assertEqual(s["grand_total"], expected)

    def test_estimate_persists_country_so_a_reload_agrees(self):
        self._estimate("US")
        page = self.client.get(reverse("checkout"))
        self.assertEqual(round(float(page.context["shipping_cost"]), 2),
                         round(self._estimate("US").json()["summary"]["shipping_cost"], 2))

    def test_checkout_page_exposes_repaint_hooks(self):
        html = self.client.get(reverse("checkout")).content.decode()
        for hook in ("data-summary-lines", "data-sum-shipping", "data-sum-grand",
                     "data-sum-tax", "data-sum-subtotal", "shippingMethodInput"):
            self.assertIn(hook, html)

    def test_estimator_js_repaints_the_summary(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "greatkart" / "static" /
              "js" / "shipping-estimate.js").read_text(encoding="utf-8")
        self.assertIn("paintSummary", js)
        self.assertIn("data-summary-lines", js)
        self.assertIn("data-sum-grand", js)

    def test_rate_limited_response_has_no_summary(self):
        for _ in range(45):
            self._estimate("IT")
        resp = self._estimate("IT")
        if resp.status_code == 429:
            self.assertNotIn("summary", resp.json())


@override_settings(SHIPPING_USE_PRINTIFY=False, STORE_TAX_RATE=2.0,
                   SHIPPING_FREE_THRESHOLD=0,
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class OrderMatchesSummaryTests(TestCase):
    """What the shopper is charged equals what the summary showed."""

    def setUp(self):
        _seed_cart(self.client, price=40)

    def test_place_order_charges_the_quoted_total(self):
        from django.core import signing
        import time

        from orders.models import Order

        self.client.post(reverse("shipping_estimate"),
                         {"country": "US", "postal_code": "78701"}, **AJAX)
        quoted = self.client.post(reverse("shipping_estimate"),
                                  {"country": "US", "postal_code": "78701"},
                                  **AJAX).json()["summary"]

        resp = self.client.post(reverse("place_order"), {
            "first_name": "A", "last_name": "B", "email": "a@b.com",
            "phone": "+15125550100", "address_line_1": "1 Main St",
            "address_line_2": "", "city": "Austin", "state": "TX",
            "country": "US", "postal_code": "78701", "order_note": "",
            "website": "", "form_ts": signing.dumps(time.time() - 10,
                                                    salt="checkout-ts"),
        })
        self.assertIn(resp.status_code, (200, 302))
        order = Order.objects.order_by("-id").first()
        self.assertIsNotNone(order)
        self.assertEqual(round(float(order.shipping_cost), 2),
                         round(quoted["shipping_cost"], 2))
        self.assertEqual(round(float(order.order_total), 2),
                         round(quoted["grand_total"], 2))
        self.assertEqual(order.shipping_method, quoted["method"])
