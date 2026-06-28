"""Phase 55: ultra-premium filters / checkout steps / quick-view focus trap.
Fictitious data; no real orders/payments."""
import pathlib

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from carts.models import Cart, CartItem
from category.models import Category
from store.models import Product, Variation

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
QV_JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "quick-view.js"


def _product(name="Tee", price=25):
    cat = Category.objects.get_or_create(category_name="Tees", slug="tees")[0]
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               description="x", price=price, stock=9999, category=cat,
                               is_available=True)
    Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
    Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    return p


def _cart(client):
    client.get(reverse("cart"))
    cart, _ = Cart.objects.get_or_create(cart_id=client.session.session_key)
    CartItem.objects.create(product=_product(), cart=cart, quantity=1, is_active=True)
    return cart


class CheckoutStepsTests(TestCase):
    def test_steps_render(self):
        _cart(self.client)
        with translation.override("en"):
            html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn("checkout-steps", html)
        self.assertIn("Details & review", html)
        self.assertIn("is-current", html)
        self.assertIn("is-done", html)
        self.assertIn('aria-current="step"', html)

    def test_steps_localized_it(self):
        _cart(self.client)
        with translation.override("it"):
            html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn("Dettagli", html)  # "Dettagli e revisione"

    def test_no_nested_form_on_checkout(self):
        _cart(self.client)
        html = self.client.get(reverse("checkout")).content.decode()
        self.assertNotIn('<form class="se-form"', html)  # estimator is a <div>


class FiltersPremiumTests(TestCase):
    def setUp(self):
        self.p = _product("Filter Tee")

    def test_filter_drawer_and_trigger_present(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn('id="filterDrawer"', html)
        self.assertIn("data-open-filters", html)
        self.assertIn('data-sortx', html)

    def test_active_chips_render_when_filtering(self):
        html = self.client.get(reverse("store") + "?min_price=10&max_price=50").content.decode()
        self.assertIn("chips-bar", html)
        self.assertIn("filter-chip-active", html)
        self.assertIn("Clear all", html)

    def test_no_chips_without_filters(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertNotIn("filter-chip-active", html)

    def test_no_gold_hover_on_filters(self):
        # regression: filter accent must not be gold (Phase 49 root-cause fix)
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".filter-form .chip-opt input{accent-color:var(--primary)", css)


class CategoryRegressionTests(TestCase):
    def test_printify_category_404(self):
        Category.objects.get_or_create(category_name="Printify", slug="printify",
                                       defaults={"is_public": False})
        self.assertEqual(self.client.get("/store/category/printify/").status_code, 404)


class QuickViewFocusTrapTests(TestCase):
    def test_js_has_focus_trap(self):
        js = QV_JS.read_text(encoding="utf-8")
        self.assertIn("focusables", js)
        self.assertIn('e.key === "Tab"', js)
        self.assertIn("lastTrigger", js)  # focus restored to trigger

    def test_drawer_is_aria_dialog(self):
        js = QV_JS.read_text(encoding="utf-8")
        self.assertIn('role="dialog"', js)
        self.assertIn('aria-modal="true"', js)


class UltraPremiumAssetTests(TestCase):
    def test_css_checkout_steps_and_dark(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".checkout-steps", css)
        self.assertIn('.cstep.is-current .cstep-dot', css)
        self.assertIn(':root[data-theme="dark"] .cstep-dot', css)

    def test_css_no_invalid_border_strong_as_color(self):
        # --border-strong is a shorthand; must never be used as background/border-color
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("background:var(--border-strong)", css)
        self.assertNotIn("border-color:var(--border-strong)", css)

    def test_sticky_summary_desktop(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".checkout-summary{position:sticky", css)
