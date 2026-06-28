"""Phase 51: pre-order shipping estimates (service, API, UI, honesty)."""
import datetime
import pathlib
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import Account
from carts.models import Cart, CartItem
from category.models import Category
from printify_integration import shipping_estimator as se
from printify_integration.models import PrintifyShippingEstimateCache, PrintifyShippingProfile
from printify_integration.printify_client import PrintifyError
from store.models import Product, Variation

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "shipping-estimate.js"

LIVE_COSTS = {"standard": 1000, "express": 5000, "priority": 3000, "economy": 399}


def _product(name="Tee", price=25, bp=145, pv=29, pid="shop123", vid="17887"):
    cat = Category.objects.get_or_create(category_name="Tees", slug="tees")[0]
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               description="x", price=price, stock=9999, category=cat,
                               is_available=True, printify_product_id=pid,
                               printify_blueprint_id=bp, printify_provider_id=pv)
    Variation.objects.create(product=p, variation_category="size", variation_value="M",
                             is_active=True, printify_variant_id=vid, printify_is_default=True)
    return p


class _StubItem:
    class _Vars:
        def all(self):
            return []

    def __init__(self, product, quantity=1):
        self.product = product
        self.quantity = quantity
        self.variations = self._Vars()
        self.printify_variant_id = None


def _mock_client(costs=None, exc=None):
    client = MagicMock()
    if exc is not None:
        client.calculate_order_shipping.side_effect = exc
    else:
        client.calculate_order_shipping.return_value = dict(costs or LIVE_COSTS)
    return client


# --------------------------------------------------------------------------- #
# Service — tiers
# --------------------------------------------------------------------------- #
@override_settings(SHIPPING_USE_PRINTIFY=True, SHIPPING_FREE_THRESHOLD=0)
class LiveEstimateTests(TestCase):
    def setUp(self):
        self.p = _product()
        self.cart = [_StubItem(self.p, quantity=1)]

    def test_live_success_sets_source_and_options(self):
        client = _mock_client()
        with patch("printify_integration.printify_client.get_client", return_value=client):
            r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertTrue(r.available)
        self.assertEqual(r.source, se.SOURCE_LIVE)
        methods = {o.method for o in r.options}
        self.assertEqual(methods, set(LIVE_COSTS))
        std = next(o for o in r.options if o.method == "standard")
        self.assertEqual(std.cost, 10.0)  # 1000 cents
        # The read-only shipping endpoint was used; no order was created.
        self.assertTrue(client.calculate_order_shipping.called)
        self.assertFalse(client.create_order.called)

    def test_live_payload_line_items_correct(self):
        client = _mock_client()
        with patch("printify_integration.printify_client.get_client", return_value=client):
            se.estimate_for_cart(self.cart, "FR", postal_code="75001", use_cache=False)
        args, kwargs = client.calculate_order_shipping.call_args
        line_items, address_to = args[0], args[1]
        self.assertEqual(line_items[0]["product_id"], "shop123")
        self.assertEqual(line_items[0]["variant_id"], 17887)
        self.assertEqual(line_items[0]["quantity"], 1)
        self.assertEqual(address_to["country"], "FR")
        self.assertEqual(address_to["zip"], "75001")

    def test_live_400_invalid_address_falls_back(self):
        client = _mock_client(exc=PrintifyError("bad", status=400))
        with patch("printify_integration.printify_client.get_client", return_value=client):
            r = se.estimate_for_cart(self.cart, "IT", postal_code="x", use_cache=False)
        self.assertTrue(r.available)
        self.assertNotEqual(r.source, se.SOURCE_LIVE)
        self.assertIn("address_invalid", r.errors_safe)

    def test_live_429_rate_limited_falls_back(self):
        client = _mock_client(exc=PrintifyError("slow", status=429))
        with patch("printify_integration.printify_client.get_client", return_value=client):
            r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertTrue(r.available)
        self.assertNotEqual(r.source, se.SOURCE_LIVE)
        self.assertIn("rate_limited", r.errors_safe)

    def test_method_selection_respected(self):
        client = _mock_client()
        with patch("printify_integration.printify_client.get_client", return_value=client):
            r = se.estimate_for_cart(self.cart, "IT", postal_code="20100",
                                     shipping_method="express", use_cache=False)
        self.assertEqual(r.selected_method, "express")
        self.assertEqual(r.shipping_cost, 50.0)


@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
class FallbackTierTests(TestCase):
    def setUp(self):
        self.p = _product()
        self.cart = [_StubItem(self.p, quantity=2)]

    def test_cached_profile_used_when_present(self):
        PrintifyShippingProfile.objects.create(
            blueprint_id=145, print_provider_id=29, country_code="IT",
            first_item_cost=5.0, additional_item_cost=2.0, currency="EUR",
            handling_days=4, min_delivery_days=7, max_delivery_days=12)
        r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertEqual(r.source, se.SOURCE_CACHED)
        self.assertEqual(r.shipping_cost, 7.0)  # 5 + 2*(2-1)

    def test_cached_profile_window_matches_profile_and_option(self):
        # Regression: the header delivery range must equal the profile's own range
        # (no double-counting transit on top) and match the selected option.
        PrintifyShippingProfile.objects.create(
            blueprint_id=145, print_provider_id=29, country_code="IT",
            first_item_cost=5.0, additional_item_cost=2.0, currency="EUR",
            handling_days=10, min_delivery_days=13, max_delivery_days=18)
        r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertEqual((r.delivery_days_min, r.delivery_days_max), (13, 18))
        self.assertEqual(r.production_days_min, 10)
        opt = r.options[0]
        self.assertEqual((opt.delivery_days_min, opt.delivery_days_max),
                         (r.delivery_days_min, r.delivery_days_max))

    def test_local_fallback_when_no_profile(self):
        r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertEqual(r.source, se.SOURCE_LOCAL)
        # IT fallback rate: first 4.90 + additional 1.90 = 6.80
        self.assertAlmostEqual(r.shipping_cost, 6.80, places=2)

    def test_additional_item_cost_scales_with_quantity(self):
        one = se.estimate_for_cart([_StubItem(self.p, 1)], "IT", use_cache=False)
        three = se.estimate_for_cart([_StubItem(self.p, 3)], "IT", use_cache=False)
        self.assertGreater(three.shipping_cost, one.shipping_cost)

    def test_unsupported_country_unavailable(self):
        r = se.estimate_for_cart(self.cart, "JP", postal_code="100", use_cache=False)
        self.assertFalse(r.available)
        self.assertIn("country_unsupported", r.errors_safe)

    def test_empty_cart_unavailable(self):
        r = se.estimate_for_cart([], "IT", use_cache=False)
        self.assertFalse(r.available)
        self.assertIn("empty_cart", r.errors_safe)

    def test_core_eu_markets_supported(self):
        for cc in ("IT", "FR", "BE"):
            r = se.estimate_for_cart(self.cart, cc, use_cache=False)
            self.assertTrue(r.available, cc)

    def test_delivery_is_production_plus_transit(self):
        r = se.estimate_for_cart(self.cart, "IT", use_cache=False)
        self.assertEqual(r.delivery_days_min, r.production_days_min + r.transit_days_min)
        self.assertEqual(r.delivery_days_max, r.production_days_max + r.transit_days_max)


@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=80)
class FreeShippingTests(TestCase):
    def test_free_when_over_threshold(self):
        p = _product(price=100)
        r = se.estimate_for_cart([_StubItem(p, 1)], "IT", use_cache=False)
        self.assertTrue(r.free)
        self.assertEqual(r.shipping_cost, 0.0)


class BusinessDayMathTests(TestCase):
    def test_skips_weekend(self):
        friday = datetime.date(2026, 1, 2)  # Friday
        self.assertEqual(se.add_business_days(friday, 1), datetime.date(2026, 1, 5))  # Mon
        self.assertEqual(se.add_business_days(friday, 3), datetime.date(2026, 1, 7))  # Wed

    def test_zero_days_returns_same(self):
        d = datetime.date(2026, 1, 2)
        self.assertEqual(se.add_business_days(d, 0), d)


class BuildLineItemsTests(TestCase):
    def test_synced_product_uses_product_id(self):
        items = [_StubItem(_product(), 2)]
        line_items, live, qty = se.build_line_items(items)
        self.assertTrue(live)
        self.assertEqual(qty, 2)
        self.assertEqual(line_items[0]["product_id"], "shop123")

    def test_blueprint_only_product_uses_blueprint_fields(self):
        p = _product(pid=None)  # no shop product id, but blueprint+provider+variant present
        line_items, live, _qty = se.build_line_items([_StubItem(p, 1)])
        self.assertTrue(live)
        self.assertEqual(line_items[0]["blueprint_id"], 145)
        self.assertEqual(line_items[0]["print_provider_id"], 29)

    def test_non_printify_product_not_live_capable(self):
        cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
        p = Product.objects.create(product_name="Plain", slug="plain", description="x",
                                   price=10, stock=5, category=cat, is_available=True)
        _li, live, _qty = se.build_line_items([_StubItem(p, 1)])
        self.assertFalse(live)


# --------------------------------------------------------------------------- #
# API endpoint
# --------------------------------------------------------------------------- #
class EstimateEndpointTests(TestCase):
    def _guest_cart(self):
        self.client.get(reverse("cart"))  # establish session
        sk = self.client.session.session_key
        cart, _ = Cart.objects.get_or_create(cart_id=sk)
        CartItem.objects.create(product=_product(), cart=cart, quantity=1, is_active=True)
        return cart

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("shipping_estimate")).status_code, 405)

    def test_csrf_required(self):
        c = self.client_class(enforce_csrf_checks=True)
        r = c.post(reverse("shipping_estimate"), {"country": "IT"})
        self.assertEqual(r.status_code, 403)

    def test_empty_cart_returns_unavailable(self):
        r = self.client.post(reverse("shipping_estimate"), {"country": "IT"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["available"])
        self.assertIn("empty_cart", r.json()["errors_safe"])

    def test_invalid_country(self):
        r = self.client.post(reverse("shipping_estimate"), {"country": "X"})
        self.assertIn("invalid_country", r.json()["errors_safe"])

    def test_guest_cart_estimate_ok(self):
        self._guest_cart()
        r = self.client.post(reverse("shipping_estimate"),
                             {"country": "IT", "postal_code": "20100"})
        data = r.json()
        self.assertTrue(data["available"])
        self.assertIn(data["source"], (se.SOURCE_CACHED, se.SOURCE_LOCAL, se.SOURCE_LIVE))
        self.assertTrue(data["options"])

    def test_logged_in_cart_estimate_ok(self):
        user = Account.objects.create_user(
            first_name="A", last_name="B", username="u1",
            email="u1@example.com", password="pw12345!")
        user.is_active = True
        user.save()
        self.client.force_login(user)
        CartItem.objects.create(product=_product(), user=user, quantity=1, is_active=True)
        r = self.client.post(reverse("shipping_estimate"),
                             {"country": "FR", "postal_code": "75001"})
        self.assertTrue(r.json()["available"])

    @override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
    def test_client_supplied_price_is_ignored(self):
        self._guest_cart()
        # Attacker tries to force a cheaper shipping via the payload.
        r = self.client.post(reverse("shipping_estimate"),
                             {"country": "IT", "postal_code": "20100",
                              "cost": "0.01", "shipping_cost": "0.01", "price": "0.01"})
        data = r.json()
        # The cost comes from the server tier, never from the client field.
        self.assertNotEqual(data["shipping_cost"], 0.01)


# --------------------------------------------------------------------------- #
# UI render + i18n
# --------------------------------------------------------------------------- #
class EstimatorUITests(TestCase):
    def _populate(self):
        self.client.get(reverse("cart"))
        sk = self.client.session.session_key
        cart, _ = Cart.objects.get_or_create(cart_id=sk)
        CartItem.objects.create(product=_product(), cart=cart, quantity=1, is_active=True)

    def test_cart_renders_estimator(self):
        self._populate()
        with translation.override("en"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("data-ship-estimator", html)
        self.assertIn("Estimate delivery", html)
        self.assertIn("shipping-estimate.js", html)

    def test_checkout_binds_to_address_fields(self):
        self._populate()
        with translation.override("en"):
            html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn('data-country-from="countryInput"', html)
        self.assertIn('data-zip-from="postalCodeInput"', html)
        self.assertNotIn("data-se-country", html)  # internal fields suppressed on checkout

    def test_checkout_estimator_is_not_a_nested_form(self):
        # Regression: a nested <form> inside the checkout billing form is invalid
        # HTML and made the estimate button submit the order. It must be a <div>
        # with a type="button" trigger.
        self._populate()
        with translation.override("en"):
            html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn('<div class="se-form"', html)
        self.assertIn('type="button" class="btn btn-primary se-btn" data-se-submit', html)
        # The estimator must NOT be a (nested) form.
        self.assertNotIn('<form class="se-form"', html)

    def test_localized_it(self):
        self._populate()
        with translation.override("it"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("Stima consegna", html)

    def test_localized_fr(self):
        self._populate()
        with translation.override("fr"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("Estimer la livraison", html)


class EstimatorAssetTests(TestCase):
    def test_css_has_dark_overrides(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".ship-estimator", css)
        self.assertIn(':root[data-theme="dark"] .se-option.is-selected', css)

    def test_css_mobile_single_column(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width:575.98px)", css)
        self.assertIn(".se-fields{grid-template-columns:1fr;}", css)

    def test_css_no_gold_accent_color_on_native_controls(self):
        css = CSS.read_text(encoding="utf-8")
        # Estimator must not reintroduce the tinted-hover bug.
        self.assertNotIn(".se-option-radio{accent-color:var(--accent)", css)

    def test_js_never_posts_price(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('body.set("country"', js)
        self.assertNotIn('body.set("cost"', js)
        self.assertNotIn('body.set("price"', js)


# --------------------------------------------------------------------------- #
# Honesty / privacy
# --------------------------------------------------------------------------- #
@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
class HonestyTests(TestCase):
    def setUp(self):
        self.cart = [_StubItem(_product(), 1)]

    def test_source_label_is_honest(self):
        with translation.override("en"):
            r = se.estimate_for_cart(self.cart, "IT", use_cache=False)
            self.assertEqual(r.source_label, "Estimated")

    def test_live_source_label(self):
        client = _mock_client()
        with override_settings(SHIPPING_USE_PRINTIFY=True), translation.override("en"), \
                patch("printify_integration.printify_client.get_client", return_value=client):
            r = se.estimate_for_cart(self.cart, "IT", postal_code="20100", use_cache=False)
        self.assertEqual(r.source_label, "Estimated by Printify")

    def test_disclaimer_present(self):
        with translation.override("en"):
            r = se.estimate_for_cart(self.cart, "IT", use_cache=False)
        self.assertTrue(r.disclaimer)

    def test_no_internal_ids_or_raw_in_payload(self):
        r = se.estimate_for_cart(self.cart, "IT", use_cache=False)
        data = r.as_dict()
        forbidden = {"blueprint_id", "print_provider_id", "printify_variant_id",
                     "raw", "raw_response", "token", "sku"}
        self.assertFalse(forbidden & set(data.keys()))
        for opt in data["options"]:
            self.assertFalse(forbidden & set(opt.keys()))

    def test_cache_stores_no_pii(self):
        se.estimate_for_cart(self.cart, "IT", postal_code="20100ABCDEF", use_cache=True)
        row = PrintifyShippingEstimateCache.objects.first()
        self.assertIsNotNone(row)
        # Only a postal PREFIX is persisted, never the full code.
        self.assertEqual(row.postal_prefix, "201")
        self.assertNotIn("ABCDEF", row.postal_prefix)
