"""Phase 45: cart remove modal, transparent surfaces, sortx-style variant dropdowns,
nav visibility, filter hover."""
import pathlib

from django.test import TestCase
from django.conf import settings
from django.urls import reverse

from category.models import Category
from store.models import Product, Variation

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "variant-select.js"


def _product(name="Tee"):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    p = Product.objects.create(product_name=name, slug=name.lower(), description="x",
                               price=25, stock=9999, category=cat, is_available=True)
    Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
    Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    return p


class CartRemoveModalTests(TestCase):
    def test_cart_uses_premium_modal_not_confirm(self):
        html = self.client.get(reverse("cart")).content.decode()
        # the remove flow no longer uses a native confirm() onclick handler
        self.assertNotIn('onclick="return confirm', html)
        self.assertNotIn("onclick='return confirm", html)

    def test_remove_links_trigger_modal(self):
        # with an item present, remove links carry the data-cart-remove hook + the modal exists
        from django.utils import translation
        p = _product("Removable")
        self.client.post(reverse("add_cart", args=[p.id]), {"color": "Black", "size": "M"})
        with translation.override("en"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("data-cart-remove", html)
        self.assertIn('id="cartRemoveModal"', html)
        self.assertIn("Remove this item from your cart?", html)

    def test_modal_subtext_present(self):
        from django.utils import translation
        with translation.override("en"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("You can always add it again later.", html)

    def test_modal_subtext_localized_fr(self):
        from django.utils import translation
        with translation.override("fr"):
            html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("Vous pourrez toujours", html)


class CartSurfaceTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_cart_card_transparent(self):
        self.assertIn(".cart-card{background:transparent!important;border:0!important", self.css)

    def test_qty_control_no_border(self):
        self.assertIn(".qty-control{border:0!important", self.css)

    def test_empty_card_no_border(self):
        self.assertIn(".cart-empty-card{border:0!important;background:transparent!important", self.css)


class VariantDropdownTests(TestCase):
    def setUp(self):
        self.p = _product("Dropdowns")

    def test_dropdowns_are_vanilla_not_bootstrap(self):
        html = self.client.get(self.p.get_url()).content.decode()
        # the colour/size toggles no longer use Bootstrap data-toggle (no double-open)
        self.assertIn("data-csdd", html)
        self.assertIn("data-csdd-toggle", html)
        self.assertNotIn('id="colorDropdown"\n                data-toggle="dropdown"', html)

    def test_variant_select_js_loaded(self):
        html = self.client.get(self.p.get_url()).content.decode()
        self.assertIn("variant-select.js", html)

    def test_dropdown_styled_like_sortx(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".custom-select-btn", css)
        self.assertIn(".csdd-caret", css)
        # chevron rotates on open like the sort dropdown
        self.assertIn(".custom-select-dd.is-open .csdd-caret{transform:rotate(180deg)", css)


class FilterHoverTests(TestCase):
    def test_filter_accent_not_gold(self):
        css = CSS.read_text(encoding="utf-8")
        # native control accent-color switched from gold (--accent) to brand primary
        self.assertIn(".filter-form .rating-opt input,\n.filter-form .toggle-opt input,\n"
                      ".filter-form .chip-opt input{accent-color:var(--primary);}", css)

    def test_no_section_wide_hover(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".filter-form .filter-section:hover,", css)
        self.assertIn("background:transparent;}", css)


class NavVisibilityTests(TestCase):
    def test_nav_fit_rules_present(self):
        css = CSS.read_text(encoding="utf-8")
        # the collapse no longer grows to squash the search; search absorbs the slack
        self.assertIn(".premium-nav .navbar-collapse{flex:0 0 auto!important", css)
        self.assertIn(".premium-nav > .container{justify-content:flex-start!important;}", css)
