"""Phase 54: wow polish + smart features (quick view, search, recommendations,
micro-interactions). Fictitious data; no real orders/payments."""
import pathlib

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from category.models import Category
from merchandising.recommendations import recommend_for_product
from store.models import Product, Variation

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
QV_JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "quick-view.js"
SEARCH_JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "search.js"
WISH_JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "wishlist.js"


def _product(name="Tee", price=25, cat=None, with_vars=True):
    cat = cat or Category.objects.get_or_create(category_name="Tees", slug="tees")[0]
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               description="x", price=price, stock=9999, category=cat,
                               is_available=True, printify_product_id="qv-" + name.lower(),
                               printify_blueprint_id=145, printify_provider_id=29)
    if with_vars:
        Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
        Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    return p


class QuickViewTests(TestCase):
    def setUp(self):
        self.p = _product("Quick Tee")

    def test_endpoint_renders_fragment(self):
        r = self.client.get(reverse("quick_view", args=[self.p.id]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("qv-form", html)
        self.assertIn(reverse("add_cart", args=[self.p.id]), html)
        self.assertIn('select name="color"', html)
        self.assertIn('select name="size"', html)
        self.assertIn("View full details", html)

    def test_missing_product_404(self):
        self.assertEqual(self.client.get(reverse("quick_view", args=[999999])).status_code, 404)

    def test_unavailable_product_404(self):
        self.p.is_available = False
        self.p.save()
        self.assertEqual(self.client.get(reverse("quick_view", args=[self.p.id])).status_code, 404)

    def test_no_internal_printify_or_cost_leak(self):
        html = self.client.get(reverse("quick_view", args=[self.p.id])).content.decode().lower()
        for token in ("printify_blueprint", "printify_provider", "cost_production",
                      "cost_shipping", "printify_variant"):
            self.assertNotIn(token, html)

    def test_store_grid_has_quick_view_trigger(self):
        with translation.override("en"):
            html = self.client.get(reverse("store")).content.decode()
        self.assertIn('data-quick-view="%d"' % self.p.id, html)
        self.assertIn("quick-view.js", html)

    def test_localized_it(self):
        with translation.override("it"):
            html = self.client.get(reverse("quick_view", args=[self.p.id])).content.decode()
        self.assertIn("Aggiungi al carrello", html)

    def test_localized_fr(self):
        with translation.override("fr"):
            html = self.client.get(reverse("quick_view", args=[self.p.id])).content.decode()
        self.assertIn("Ajouter au panier", html)


class SmartRecommendationsTests(TestCase):
    def test_excludes_current_product(self):
        cat = Category.objects.get_or_create(category_name="Tees", slug="tees")[0]
        cur = _product("Current", 50, cat)
        _product("Other", 55, cat)
        recs = recommend_for_product(cur, limit=4)
        self.assertNotIn(cur.id, [r.id for r in recs])

    def test_price_proximity_ranking(self):
        cat = Category.objects.get_or_create(category_name="Price", slug="price")[0]
        cur = _product("Anchor", 50, cat)
        near = _product("Near", 51, cat)       # diff 1
        mid = _product("Mid", 60, cat)         # diff 10
        far = _product("Far", 200, cat)        # diff 150
        recs = recommend_for_product(cur, limit=3)
        ids = [r.id for r in recs]
        # closest price first
        self.assertEqual(ids[0], near.id)
        self.assertLess(ids.index(mid.id), ids.index(far.id))

    def test_only_available_products(self):
        cat = Category.objects.get_or_create(category_name="Av", slug="av")[0]
        cur = _product("Cur", 50, cat)
        gone = _product("Gone", 51, cat)
        gone.is_available = False
        gone.save()
        recs = recommend_for_product(cur, limit=4)
        self.assertNotIn(gone.id, [r.id for r in recs])


class PdpWowTests(TestCase):
    def test_pairs_well_with_badge(self):
        # The badge labels the Complete-the-look section, which renders only when
        # there are curated pairings -> create one.
        from merchandising.models import ProductRelation
        p = _product("Pairs Tee")
        other = _product("Pairs Partner")
        ProductRelation.objects.create(from_product=p, to_product=other,
                                       relation_type=ProductRelation.COMPLETE_LOOK, is_active=True)
        with translation.override("en"):
            html = self.client.get(p.get_url()).content.decode()
        self.assertIn("Pairs well with", html)

    def test_size_guide_present(self):
        p = _product("Guide Tee")
        html = self.client.get(p.get_url()).content.decode()
        self.assertIn("Size guide", html)
        self.assertIn('id="sizeGuide"', html)


class SearchPremiumTests(TestCase):
    def test_navbar_has_recent_and_popular_hooks(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-ac-popular", html)
        self.assertIn("data-ac-recent-label", html)

    def test_search_js_has_recent_searches(self):
        js = SEARCH_JS.read_text(encoding="utf-8")
        self.assertIn("gk_recent_searches", js)
        self.assertIn("renderEmpty", js)

    def test_wishlist_js_uses_delegation(self):
        # delegated listener => dynamically-injected hearts (quick view) work
        js = WISH_JS.read_text(encoding="utf-8")
        self.assertIn('addEventListener("click"', js)
        self.assertIn("data-wishlist-toggle", js)


class WowAssetTests(TestCase):
    def test_css_quick_view_and_dark(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".qv-backdrop", css)
        self.assertIn(".qv-drawer", css)
        self.assertIn(":root[data-theme=\"dark\"] .qv-sk-media", css)

    def test_css_respects_reduced_motion(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion:reduce)", css)

    def test_quick_view_js_no_order_creation(self):
        js = QV_JS.read_text(encoding="utf-8")
        # quick view never posts an order itself; add-to-cart uses the normal form
        self.assertNotIn("place_order", js)
        self.assertIn("data-quick-view", js)
