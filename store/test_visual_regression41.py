"""Phase 41: root-cause regressions — home de-dup, sort dropdown, PDP hierarchy, search."""
from django.test import TestCase
from django.urls import reverse

from category.models import Category
from store.models import Product, Variation


def _product(name="Tee", **kw):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description="Soft tee",
             price=20, stock=5, category=cat, is_available=True,
             printify_blueprint_id=145, printify_provider_id=99, printify_provider_name="P",
             composition="100% cotton")
    d.update(kw)
    return Product.objects.create(**d)


class HomeDeDupTests(TestCase):
    def test_redundant_quote_section_removed(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("Our philosophy", html)
        self.assertNotIn("Fewer, better things", html)

    def test_why_us_features_are_brand_value_not_duplicated_trust(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Honest pricing", html)
        self.assertIn("Designed to last", html)
        # the why-us no longer repeats the trust strip's "Secure & simple" card
        self.assertNotIn("Secure &amp; simple", html)

    def test_trust_strip_not_premium_duplicate(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Ethically printed on demand", html)


class SortDropdownTests(TestCase):
    def test_uses_robust_vanilla_sortx_not_bootstrap(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-sortx", html)
        self.assertIn("sortx-menu", html)
        # the fragile bootstrap sort dropdown is gone
        self.assertNotIn("dropdown-toggle sort-btn", html)

    def test_single_sort_menu(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertEqual(html.count('class="sortx-menu"'), 1)


class PdpHierarchyTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
        self.p = _product("Sweet")
        Variation.objects.create(product=self.p, variation_category="color",
                                 variation_value="Black", is_active=True)

    def test_shipping_returns_not_in_more_info_list(self):
        html = self.client.get(self.p.get_url()).content.decode()
        # the "More information" list no longer restates Shipping:/Returns: (covered by trust line)
        self.assertNotIn("<strong>Shipping</strong>:", html)
        self.assertNotIn("<strong>Returns</strong>:", html)

    def test_pod_card_is_production_focused_only(self):
        html = self.client.get(self.p.get_url()).content.decode()
        self.assertIn("Made on demand", html)
        self.assertIn("Printed to order", html)
        # no internal leaks
        self.assertNotIn("blueprint", html.lower())
        self.assertNotIn("provider_id", html.lower())


class SearchPlaceholderTests(TestCase):
    def test_shorter_placeholder(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Search products, collections", html)
        # the longer variant that overflowed is gone
        self.assertNotIn("collections, colours", html)
