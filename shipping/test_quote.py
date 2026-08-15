"""Single source of truth for checkout money (shipping/quote.py).

Before this module the Order summary was priced by `shipping.services.quote_for_cart`
(settings rate table, IP-detected country) while the "Estimate delivery" widget was
priced by `printify_integration.shipping_estimator` (Printify profiles, form country).
They disagreed even on the same country. `checkout_quote()` is now the ONE engine:
the summary, the widget, place_order and the payment payloads all read from it.
"""
from django.test import TestCase, override_settings

from category.models import Category
from carts.models import Cart, CartItem
from shipping.quote import checkout_quote
from store.models import Product, Variation


def _cart(price=25, qty=1, express=True):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    product = Product.objects.create(
        product_name="Quote Tee", slug="quote-tee", price=price, stock=10,
        category=cat, printify_express_eligible=express,
        printify_express_enabled=express)
    cart = Cart.objects.create(cart_id="quote-session")
    item = CartItem.objects.create(product=product, cart=cart, quantity=qty,
                                   is_active=True)
    return [item], product


@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0,
                   STORE_TAX_RATE=2.0)
class QuoteConsistencyTests(TestCase):
    def test_summary_and_options_share_one_shipping_number(self):
        items, _ = _cart()
        q = checkout_quote(items, country="IT")
        selected = [o for o in q.options if o["selected"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(round(selected[0]["cost"], 2), round(q.shipping_cost, 2))

    def test_totals_add_up(self):
        items, _ = _cart(price=25, qty=2)
        q = checkout_quote(items, country="IT")
        self.assertEqual(q.items_subtotal, 50.0)
        expected = round(q.items_subtotal + q.tax + q.shipping_cost - q.discount, 2)
        self.assertEqual(q.grand_total, expected)

    def test_country_change_changes_shipping(self):
        items, _ = _cart()
        it = checkout_quote(items, country="IT")
        us = checkout_quote(items, country="US")
        self.assertNotEqual(it.shipping_cost, us.shipping_cost)
        self.assertNotEqual(it.grand_total, us.grand_total)

    def test_discount_is_applied_to_grand_total(self):
        items, _ = _cart(price=100)
        plain = checkout_quote(items, country="IT")
        with_discount = checkout_quote(items, country="IT", discount=10)
        self.assertEqual(round(plain.grand_total - with_discount.grand_total, 2), 10.0)

    def test_free_shipping_threshold_zeroes_shipping(self):
        items, _ = _cart(price=200)
        with override_settings(SHIPPING_FREE_THRESHOLD=80):
            q = checkout_quote(items, country="IT")
        self.assertEqual(q.shipping_cost, 0.0)
        self.assertTrue(q.free)

    def test_unsupported_country_is_unavailable_not_zero(self):
        items, _ = _cart()
        with override_settings(SHIPPING_SUPPORTED_COUNTRIES=["IT"]):
            q = checkout_quote(items, country="JP")
        self.assertFalse(q.available)
        self.assertTrue(q.message)
        # honest: never silently price an unsupported destination as free
        self.assertEqual(q.shipping_cost, 0.0)

    def test_empty_cart_is_unavailable(self):
        q = checkout_quote([], country="IT")
        self.assertFalse(q.available)

    def test_as_dict_is_json_safe_and_has_display_strings(self):
        items, _ = _cart()
        data = checkout_quote(items, country="IT").as_dict()
        import json
        json.dumps(data)          # must not raise
        for key in ("items_subtotal", "shipping_cost", "tax", "grand_total",
                    "shipping_display", "grand_total_display", "options",
                    "method", "available", "delivery_label"):
            self.assertIn(key, data)


@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
class ExpressOfferingTests(TestCase):
    """Express is only ever offered when Printify priced it AND every rule passes."""

    def test_no_express_option_without_live_pricing(self):
        items, _ = _cart()
        q = checkout_quote(items, country="US", state="CA",
                           address1="1 Main St", phone="+15550100")
        self.assertNotIn("printify_express", [o["method"] for o in q.options])

    def test_express_offered_for_eligible_us_cart_with_live_costs(self):
        items, _ = _cart()
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="+15550100",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        methods = [o["method"] for o in q.options]
        self.assertIn("printify_express", methods)
        express = [o for o in q.options if o["method"] == "printify_express"][0]
        self.assertEqual(express["cost"], 7.99)
        self.assertTrue(express["fastest"])

    def test_express_hidden_for_belgium_even_when_priced(self):
        items, _ = _cart()
        q = checkout_quote(items, country="BE", address1="Rue 1", phone="+3222222222",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        self.assertNotIn("printify_express", [o["method"] for o in q.options])
        self.assertIn("destination_not_supported", q.express_blockers)

    def test_express_hidden_for_alaska_and_po_box(self):
        items, _ = _cart()
        for kwargs in ({"state": "AK", "address1": "1 Main St"},
                       {"state": "CA", "address1": "PO Box 9"}):
            q = checkout_quote(items, country="US", phone="+15550100",
                               _cost_map_cents={"standard": 499, "printify_express": 799},
                               **kwargs)
            self.assertNotIn("printify_express", [o["method"] for o in q.options], kwargs)

    def test_express_hidden_when_product_not_eligible(self):
        items, _ = _cart(express=False)
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="+15550100",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        self.assertNotIn("printify_express", [o["method"] for o in q.options])
        self.assertIn("items_not_eligible", q.express_blockers)

    def test_missing_phone_surfaces_actionable_blocker(self):
        items, _ = _cart()
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        self.assertIn("phone_required", q.express_blockers)
        self.assertNotIn("printify_express", [o["method"] for o in q.options])

    def test_selecting_express_prices_the_order_with_express(self):
        items, _ = _cart()
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="+15550100", method="printify_express",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        self.assertEqual(q.method, "printify_express")
        self.assertEqual(q.shipping_cost, 7.99)

    def test_ineligible_method_request_falls_back_to_standard(self):
        items, _ = _cart(express=False)
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="+15550100", method="printify_express",
                           _cost_map_cents={"standard": 499, "printify_express": 799})
        self.assertEqual(q.method, "standard")
        self.assertEqual(q.shipping_cost, 4.99)

    def test_priority_offered_when_printify_prices_it(self):
        items, _ = _cart()
        q = checkout_quote(items, country="BE", address1="Rue 1", phone="+3222222222",
                           _cost_map_cents={"standard": 499, "priority": 1299})
        methods = [o["method"] for o in q.options]
        self.assertIn("priority", methods)
        self.assertIn("standard", methods)


@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
class ReviewHardeningTests(TestCase):
    """Regressions found by the adversarial review of this phase."""

    def test_plain_express_key_obeys_the_same_gate(self):
        """Printify's cost map carries BOTH "express" and "printify_express", and
        both route to the express endpoint — so both must pass eligibility."""
        items, _ = _cart(express=False)
        q = checkout_quote(items, country="BE", address1="Rue 1", phone="",
                           _cost_map_cents={"standard": 499, "express": 5000,
                                            "printify_express": 799})
        methods = [o["method"] for o in q.options]
        self.assertNotIn("express", methods)
        self.assertNotIn("printify_express", methods)

    def test_plain_express_offered_when_eligible(self):
        items, _ = _cart(express=True)
        q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                           phone="+15550100",
                           _cost_map_cents={"standard": 499, "express": 5000})
        express = [o for o in q.options if o["method"] == "express"]
        self.assertEqual(len(express), 1)
        self.assertTrue(express[0]["fastest"])

    def test_premium_methods_are_never_offered_at_the_standard_rate(self):
        """Without a live cost map the estimator would label its single fallback
        option with whatever method was requested and price it from the local
        rate table — charging standard for a premium service."""
        items, _ = _cart(express=True)
        for requested in ("express", "printify_express", "priority", "economy"):
            q = checkout_quote(items, country="US", state="CA", address1="1 Main St",
                               phone="+15550100", method=requested)
            self.assertEqual([o["method"] for o in q.options], ["standard"], requested)
            self.assertEqual(q.method, "standard", requested)

    def test_selecting_a_premium_method_cannot_be_forced_through_the_session(self):
        from shipping.express import is_express
        items, _ = _cart(express=False)
        q = checkout_quote(items, country="IT", method="express")
        self.assertFalse(is_express(q.method))


@override_settings(SHIPPING_USE_PRINTIFY=False, STORE_TAX_RATE=2.0,
                   SHIPPING_FREE_THRESHOLD=0)
class UnavailableDestinationTests(TestCase):
    """A destination the canonical engine will not price must still be charged
    correctly by the legacy rate table — never rendered as free."""

    def test_uncurated_country_keeps_shipping_and_discount(self):
        from orders.totals import compute_cart_totals
        items, _ = _cart(price=50)
        totals = compute_cart_totals(items, "PL", discount=10.0)
        self.assertGreater(totals.shipping_cost, 0)
        expected = round(totals.items_subtotal + totals.tax
                         + totals.shipping_cost - 10.0, 2)
        self.assertEqual(totals.grand_total, expected)

    def test_curated_country_unchanged(self):
        from orders.totals import compute_cart_totals
        items, _ = _cart(price=50)
        totals = compute_cart_totals(items, "IT", discount=10.0)
        self.assertGreater(totals.shipping_cost, 0)
        self.assertEqual(totals.grand_total,
                         round(totals.items_subtotal + totals.tax
                               + totals.shipping_cost - 10.0, 2))
