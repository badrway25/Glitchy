"""Phase 32: shipping profiles, print areas, margin-after-refund, CLI, safety."""
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from category.models import Category
from store.models import Product
from printify_integration.models import PrintifyPrintArea, PrintifyShippingProfile


def _product(name="Tee", **kw):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    d = dict(product_name=name, slug=name.lower(), description="x", price=20, stock=5,
             category=cat, printify_blueprint_id=145, printify_provider_id=99,
             printify_product_id="pp_" + name)
    d.update(kw)
    return Product.objects.create(**d)


FAKE_SHIPPING = {
    "handling_time": {"value": 10, "unit": "day"},
    "profiles": [
        {"countries": ["US"], "first_item": {"cost": 399, "currency": "USD"},
         "additional_items": {"cost": 209, "currency": "USD"}, "variant_ids": [1]},
        {"countries": ["REST_OF_THE_WORLD"], "first_item": {"cost": 1000, "currency": "USD"},
         "additional_items": {"cost": 400, "currency": "USD"}, "variant_ids": [1]},
    ],
}
FAKE_PRODUCT = {
    "blueprint_id": 145, "print_provider_id": 99,
    "print_areas": [{"variant_ids": [1, 2, 3], "placeholders": [
        {"position": "front", "images": [{"id": "i1"}]},
        {"position": "neck", "images": []}]}],
}


class ShippingProfileTests(TestCase):
    def test_import_creates_per_country_rows(self):
        from printify_integration.profiles import import_shipping_profiles
        with patch("printify_integration.printify_client.PrintifyClient.get_shipping_info",
                   return_value=FAKE_SHIPPING):
            s = import_shipping_profiles(145, 99, countries=["US", "IT", "FR"])
        self.assertEqual(s["created"], 3)
        us = PrintifyShippingProfile.objects.get(country_code="US")
        self.assertEqual(us.first_item_cost, 3.99)
        it = PrintifyShippingProfile.objects.get(country_code="IT")   # REST_OF_THE_WORLD
        self.assertEqual(it.first_item_cost, 10.0)

    def test_import_is_idempotent(self):
        from printify_integration.profiles import import_shipping_profiles
        with patch("printify_integration.printify_client.PrintifyClient.get_shipping_info",
                   return_value=FAKE_SHIPPING):
            import_shipping_profiles(145, 99, countries=["US"])
            import_shipping_profiles(145, 99, countries=["US"])
        self.assertEqual(PrintifyShippingProfile.objects.filter(country_code="US").count(), 1)

    def test_import_fallback_on_api_error(self):
        from printify_integration.profiles import import_shipping_profiles
        with patch("printify_integration.printify_client.PrintifyClient.get_shipping_info",
                   side_effect=TimeoutError("down")):
            s = import_shipping_profiles(145, 99, countries=["US"])
        self.assertIsNotNone(s["error"])
        self.assertEqual(PrintifyShippingProfile.objects.count(), 0)   # nothing written

    def test_sync_command_dry_run_writes_nothing(self):
        _product("Cmd")
        out = StringIO()
        with patch("printify_integration.printify_client.PrintifyClient.get_shipping_info",
                   return_value=FAKE_SHIPPING):
            call_command("printify_sync_shipping_profiles", "--country", "US", stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertEqual(PrintifyShippingProfile.objects.count(), 0)

    def test_sync_command_apply_and_json(self):
        _product("Cmd2")
        out = StringIO()
        with patch("printify_integration.printify_client.PrintifyClient.get_shipping_info",
                   return_value=FAKE_SHIPPING):
            call_command("printify_sync_shipping_profiles", "--apply", "--country", "US",
                         "--json", stdout=out)
        self.assertIn('"mode"', out.getvalue())
        self.assertTrue(PrintifyShippingProfile.objects.filter(country_code="US").exists())


class PrintAreaTests(TestCase):
    def test_import_print_areas_maps_positions(self):
        from printify_integration.profiles import import_print_areas
        p = _product("PA")
        r = import_print_areas(p, FAKE_PRODUCT)
        self.assertEqual(set(r["positions"]), {"front", "neck"})
        front = PrintifyPrintArea.objects.get(product=p, position="front")
        self.assertTrue(front.has_print_file)
        neck = PrintifyPrintArea.objects.get(product=p, position="neck")
        self.assertFalse(neck.has_print_file)        # missing print file detected
        self.assertEqual(front.variant_count, 3)

    def test_print_areas_not_customer_facing(self):
        p = _product("PA2")
        from printify_integration.profiles import import_print_areas
        import_print_areas(p, FAKE_PRODUCT)
        html = self.client.get(p.get_url()).content.decode().lower()
        # technical print-area internals must never reach the customer page
        for leak in ("print_area", "print_provider_id", "blueprint_id", "has_print_file",
                     "placeholder_count", "pp_pa2"):
            self.assertNotIn(leak, html)


class MarginAfterRefundTests(TestCase):
    def test_full_refund_can_go_negative(self):
        from printify_integration.margin_simulator import simulate_margin_after_refund
        p = _product("R1", price=20, base_cost=10)
        s = simulate_margin_after_refund(product=p, quantity=1, country="IT",
                                         shipping_source="fallback", refund_type="full")
        self.assertEqual(s.refund_amount, 20.0)
        self.assertTrue(s.negative_after_refund)     # lost production + fee
        self.assertIn("Refund", s.explanation)

    def test_partial_refund(self):
        from printify_integration.margin_simulator import simulate_margin_after_refund
        p = _product("R2", price=40, base_cost=8)
        s = simulate_margin_after_refund(product=p, quantity=1, country="IT",
                                         shipping_source="fallback",
                                         refund_type="partial", partial_amount=5)
        self.assertEqual(s.refund_amount, 5.0)
        self.assertFalse(s.negative_after_refund)

    def test_shipping_refunded_increases_refund(self):
        from printify_integration.margin_simulator import simulate_margin_after_refund
        p = _product("R3", price=30, base_cost=8)
        no_ship = simulate_margin_after_refund(product=p, country="IT",
                                               shipping_source="fallback", refund_type="full")
        with_ship = simulate_margin_after_refund(product=p, country="IT",
                                                 shipping_source="fallback", refund_type="full",
                                                 shipping_refunded=True)
        self.assertGreater(with_ship.refund_amount, no_ship.refund_amount)

    def test_creates_no_orders(self):
        from orders.models import Order
        from printify_integration.margin_simulator import simulate_margin_after_refund
        p = _product("R4", base_cost=8)
        before = Order.objects.count()
        simulate_margin_after_refund(product=p, country="IT", shipping_source="fallback")
        self.assertEqual(Order.objects.count(), before)
