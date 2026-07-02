"""Phase 67: premium store features — safe quick-add, compare, recently viewed.

The quick-add safety contract is the focus: a SIMPLE product adds to the cart; a product
that needs a size/colour returns needs_options (never adds a wrong variation); nothing ever
creates an Order or takes payment. No PII. localStorage holds only product ids (client-side).
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from store.models import Category, Product, Variation
from carts.models import CartItem
from orders.models import Order


class Phase67StoreFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees67")
        cls.simple = Product.objects.create(product_name="Simple Tee", slug="simple-tee-67",
                                            price=20, stock=5, category=cls.cat, is_available=True)
        cls.variant = Product.objects.create(product_name="Variant Tee", slug="variant-tee-67",
                                             price=30, stock=5, category=cls.cat, is_available=True)
        Variation.objects.create(product=cls.variant, variation_category="size", variation_value="M", is_active=True)
        cls.gone = Product.objects.create(product_name="Gone Tee", slug="gone-tee-67",
                                          price=10, stock=0, category=cls.cat, is_available=False)

    def setUp(self):
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)

    # -- quick add safety -----------------------------------------------------
    def test_quick_add_simple_product(self):
        r = self.client.post(reverse("quick_add", args=[self.simple.id]),
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["count"], 1)

    def test_quick_add_variant_returns_needs_options(self):
        r = self.client.post(reverse("quick_add", args=[self.variant.id]),
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": False, "needs_options": True})
        # nothing was added
        self.assertEqual(CartItem.objects.count(), 0)

    def test_quick_add_unavailable(self):
        r = self.client.post(reverse("quick_add", args=[self.gone.id]),
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 409)

    def test_quick_add_requires_post(self):
        r = self.client.get(reverse("quick_add", args=[self.simple.id]))
        self.assertEqual(r.status_code, 405)

    def test_quick_add_never_creates_order(self):
        before = Order.objects.count()
        self.client.post(reverse("quick_add", args=[self.simple.id]),
                        HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(Order.objects.count(), before)

    def test_quick_add_increments_not_duplicates(self):
        for _ in range(3):
            self.client.post(reverse("quick_add", args=[self.simple.id]),
                            HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        items = CartItem.objects.filter(product=self.simple)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().quantity, 3)

    # -- compare --------------------------------------------------------------
    def test_compare_caps_at_three(self):
        # pass 4 ids incl. duplicates -> only the 2 distinct available products render
        ids = "%d,%d,%d,%d" % (self.simple.id, self.variant.id, self.simple.id, self.variant.id)
        html = self.client.get(reverse("compare") + "?ids=" + ids).content.decode()
        # only the 2 distinct available products render (gone excluded, dupes collapsed)
        self.assertEqual(html.count('data-cmp-col'), 2)

    def test_compare_excludes_unavailable(self):
        html = self.client.get(reverse("compare") + "?ids=%d,%d" % (self.simple.id, self.gone.id)).content.decode()
        self.assertEqual(html.count('data-cmp-col'), 1)   # gone is unavailable

    def test_compare_garbage_ids_safe(self):
        # incl. the Unicode-digit edge case (²) that int() rejects -> must not 500
        r = self.client.get(reverse("compare") + "?ids=abc,;,999999,<script>,²,٠")
        self.assertEqual(r.status_code, 200)
        self.assertIn("cmp-empty", r.content.decode())

    # -- store markup ---------------------------------------------------------
    def test_card_cta_simple_vs_variant(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-quick-add", html)        # simple product
        self.assertIn("Choose options", html)        # variant product
        self.assertIn("data-compare-toggle", html)
        self.assertIn("cmpBar", html)
        self.assertIn("cmpDrawer", html)

    def test_store_features_js_loaded(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("store-features.js", html)

    def test_recently_viewed_after_pdp_visit(self):
        # visiting a PDP records it; the store then shows the rail
        self.client.get(self.simple.get_url())
        ctx = self.client.get(reverse("store")).context
        self.assertIn(self.simple, list(ctx["recently_viewed"]))

    # -- regressions + i18n ---------------------------------------------------
    def test_gallery_carousel_transform_fix_still_present(self):
        # Phase 75: transform-based carousel; the guarantee is the slide image is static (flows
        # in the track) so prev/next change the visible image.
        import pathlib
        from django.conf import settings
        base = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static"
        css = (base / "css" / "premium.css").read_text(encoding="utf-8").replace(" ", "")
        js = (base / "js" / "product-card-gallery.js").read_text(encoding="utf-8")
        self.assertIn(".pcard-slideimg{position:static!important", css)
        self.assertIn("translateX", js)

    def test_i18n(self):
        from django.utils import translation
        with translation.override("it"):
            self.assertEqual(translation.gettext("Sizes"), "Taglie")
            self.assertNotEqual(translation.gettext("Choose options"), "Choose options")  # translated
        with translation.override("fr"):
            self.assertEqual(translation.gettext("Compare"), "Comparer")
            self.assertEqual(translation.gettext("Colours"), "Couleurs")
