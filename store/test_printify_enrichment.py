"""Phase 30: Printify enrichment, data-quality score, margin simulator, customer-UI safety."""
from django.test import TestCase

from category.models import Category
from store.models import Product, Variation


def _product(name="Tee", **kw):
    cat = Category.objects.create(category_name="Cat", slug="cat")
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description="A nice tee",
             price=20, stock=10, category=cat, is_available=True)
    d.update(kw)
    return Product.objects.create(**d)


class DataQualityTests(TestCase):
    def test_bare_product_scores_low(self):
        p = _product("Bare")
        self.assertLess(p.data_quality_score(), 60)

    def test_enriched_product_scores_high(self):
        p = _product("Rich", composition="100% cotton", fit_notes="Regular",
                     care_instructions="Wash cold", base_cost=8,
                     printify_blueprint_id=145, printify_provider_id=99,
                     printify_sync_status=Product.SYNC_SYNCED, printify_blueprint_title="Tee BP",
                     printify_provider_name="Provider X")
        from django.utils import timezone
        p.printify_synced_at = timezone.now(); p.save()
        # gallery + faq help but cost/composition/provider already push it up
        self.assertGreaterEqual(p.data_quality_score(), 55)
        self.assertIn("score", p.data_quality())
        self.assertIsInstance(p.data_quality()["missing"], list)

    def test_metadata_fields_persist(self):
        p = _product("Meta", printify_visible=False, printify_tags="a, b",
                     printify_options_summary="Sizes: 5 · Colours: 8")
        p.refresh_from_db()
        self.assertFalse(p.printify_visible)
        self.assertEqual(p.printify_options_summary, "Sizes: 5 · Colours: 8")


class MarginSimulatorTests(TestCase):
    def test_simulate_does_not_create_orders(self):
        from orders.models import Order
        from printify_integration.margin_simulator import simulate_margin
        p = _product("Sim", base_cost=8)
        before = Order.objects.count()
        s = simulate_margin(product=p, quantity=2, country="IT", coupon_pct=10,
                            shipping_source="fallback")
        self.assertEqual(Order.objects.count(), before)   # no order created
        self.assertEqual(s.quantity, 2)
        self.assertEqual(s.customer_subtotal, 40.0)
        self.assertEqual(s.discount, 4.0)
        self.assertEqual(s.supplier_production_cost, 16.0)

    def test_low_margin_warning(self):
        from printify_integration.margin_simulator import simulate_margin
        p = _product("Thin", price=10, base_cost=9)   # almost no margin
        s = simulate_margin(product=p, quantity=1, country="IT", shipping_source="fallback")
        self.assertTrue(s.low_margin_warning)

    def test_options_summary_helper(self):
        from printify_integration.services import _options_summary
        out = _options_summary([{"name": "Colors", "values": [1, 2, 3]},
                                {"type": "size", "values": [1, 2]}])
        self.assertIn("Colors: 3", out)
        self.assertIn("Size: 2", out)


class CustomerUISafetyTests(TestCase):
    def test_pdp_does_not_leak_internal_ids_or_costs(self):
        p = _product("Safe", composition="100% cotton", base_cost=7.77,
                     printify_blueprint_id=145, printify_provider_id=99,
                     printify_product_id="pp_secret_123",
                     printify_provider_name="Printify Choice")
        Variation.objects.create(product=p, variation_category="size",
                                 variation_value="m", production_cost=6.66)
        html = self.client.get(p.get_url()).content.decode()
        # internal identifiers / costs must NOT appear in customer HTML
        self.assertNotIn("pp_secret_123", html)
        self.assertNotIn("blueprint", html.lower())
        self.assertNotIn("7.77", html)     # base cost
        self.assertNotIn("6.66", html)     # variant production cost
        # but the safe production framing IS present
        self.assertIn("Made on demand", html)


class AIProductExpertContextTests(TestCase):
    def test_context_includes_enriched_data_but_not_costs_or_ids(self):
        from assistant.prompt import build_context
        p = _product("Expert", composition="100% organic cotton", fit_notes="Relaxed",
                     care_instructions="Wash cold", base_cost=7.77,
                     printify_blueprint_id=145, printify_product_id="pp_secret",
                     printify_options_summary="Sizes: 5 · Colours: 8")
        ctx = build_context([], [p], "en")
        self.assertIn("organic cotton", ctx)
        self.assertIn("Care:", ctx)
        self.assertIn("Made on demand", ctx)
        self.assertIn("Sizes: 5", ctx)
        # guardrails: no internal cost / product id in the model context
        self.assertNotIn("7.77", ctx)
        self.assertNotIn("pp_secret", ctx)
        self.assertNotIn("base_cost", ctx)
