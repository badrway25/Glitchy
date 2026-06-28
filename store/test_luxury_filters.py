"""Phase 56: luxury store filter sidebar, motion, category hero, smart features.
Fictitious data; no real orders/payments."""
import pathlib

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from category.models import Category
from store.models import Product, Variation
from store.templatetags.shopfilters import color_hex, is_light_color

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "store-luxury.js"


def _product(name="Lux Tee", price=30, cat=None):
    cat = cat or Category.objects.get_or_create(category_name="Tees", slug="tees")[0]
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               description="x", price=price, stock=9999, category=cat, is_available=True)
    Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
    Variation.objects.create(product=p, variation_category="color", variation_value="White", is_active=True)
    Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    Variation.objects.create(product=p, variation_category="size", variation_value="L", is_active=True)
    return p


class LuxurySidebarTests(TestCase):
    def setUp(self):
        self.p = _product()

    def test_sidebar_intro_and_sections(self):
        with translation.override("en"):
            html = self.client.get(reverse("store")).content.decode()
        self.assertIn("lxf-intro", html)
        self.assertIn("Refine your look", html)
        self.assertIn("data-lxf-toggle", html)
        self.assertIn('aria-expanded="true"', html)
        self.assertIn("data-lxf-body", html)
        self.assertIn("aria-controls=\"lxf-cat\"", html)

    def test_color_swatches_and_size_pills(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("lxf-swatch", html)
        self.assertIn("lxf-dot", html)
        self.assertIn("lxf-pill", html)
        self.assertIn("lxf-toggle", html)

    def test_intro_localized_it(self):
        with translation.override("it"):
            html = self.client.get(reverse("store")).content.decode()
        self.assertIn("Affina il tuo stile", html)

    def test_intro_localized_fr(self):
        with translation.override("fr"):
            html = self.client.get(reverse("store")).content.decode()
        self.assertIn("Affinez votre style", html)


class CategoryHeroTests(TestCase):
    def test_hero_on_category_page(self):
        cat = Category.objects.get_or_create(category_name="Jackets", slug="jackets")[0]
        _product("Jacket One", 90, cat)
        with translation.override("en"):
            html = self.client.get(cat.get_url()).content.decode()
        self.assertIn("cat-hero", html)
        self.assertIn("Jackets", html)
        self.assertIn("Made on demand", html)

    def test_no_hero_on_store_root(self):
        _product()
        html = self.client.get(reverse("store")).content.decode()
        self.assertNotIn('class="cat-hero"', html)

    def test_printify_category_404(self):
        Category.objects.get_or_create(category_name="Printify", slug="printify",
                                       defaults={"is_public": False})
        self.assertEqual(self.client.get("/store/category/printify/").status_code, 404)


class MobileSheetAndSavedTests(TestCase):
    def setUp(self):
        self.p = _product()

    def test_mobile_sheet_handle_and_footer(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("filter-drawer-handle", html)
        self.assertIn("filter-sheet-footer", html)
        self.assertIn("data-sheet-apply", html)

    def test_saved_filter_banner_markup(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-lxf-saved", html)
        self.assertIn("data-lxf-saved-link", html)

    def test_chips_lead_when_filtering(self):
        with translation.override("en"):
            html = self.client.get(reverse("store") + "?min_price=10").content.decode()
        self.assertIn("chips-lead", html)
        self.assertIn("Showing", html)

    def test_empty_state_category_suggestions(self):
        html = self.client.get(reverse("store") + "?min_price=99999&max_price=100000").content.decode()
        self.assertIn("lxf-empty-suggest", html)


class ColorHexFilterTests(TestCase):
    def test_known_colors(self):
        self.assertEqual(color_hex("Black"), "#1c1a17")
        self.assertEqual(color_hex("white"), "#ffffff")
        self.assertEqual(color_hex("Dark Heather"), "#6e6f72")

    def test_unknown_fallback_neutral(self):
        self.assertEqual(color_hex("rainbow-sparkle-unknown"), "#cfc8bd")
        self.assertEqual(color_hex(""), "#cfc8bd")

    def test_is_light_color(self):
        self.assertTrue(is_light_color("white"))
        self.assertFalse(is_light_color("black"))


class MotionAndCssTests(TestCase):
    def test_store_loads_motion_js(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("store-luxury.js", html)

    def test_motion_js_progressive_and_reduced_motion(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("IntersectionObserver", js)
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn("gk_filter_collapsed", js)   # collapse persistence
        self.assertIn("gk_saved_filters", js)        # saved-filter memory

    def test_css_luxury_filters_present(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lxf-section", css)
        self.assertIn(".lxf-swatch:has(input:checked)", css)
        self.assertIn(".cat-hero", css)
        self.assertIn("grid-template-rows", css)  # collapse animation

    def test_css_reduced_motion_covers_reveal(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion:reduce)", css)
        self.assertIn(".reveal{opacity:1!important", css)

    def test_no_internal_printify_in_store(self):
        html = self.client.get(reverse("store")).content.decode().lower()
        for t in ("printify_blueprint", "printify_provider", "cost_production"):
            self.assertNotIn(t, html)
