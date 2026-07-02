"""Phase 66: store product-card gallery interaction fix + premium card features.

The headline is a CSS regression guard: the gallery was unscrollable because the slides
used `scroll-snap-align:center` with `x mandatory` (which pins scrollLeft to 0). The fix is
`scroll-snap-align:start`. These tests lock that in and cover the new card swatches + trust
panel + no-N+1. No PII.
"""
import pathlib

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext

from store.models import Category, Product, ProductImage, Variation

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"


class Phase66GalleryFixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees66")
        # multi-image product with colour + size variants
        cls.multi = Product.objects.create(product_name="Gallery Tee", slug="gallery-tee-66",
                                           price=30, stock=5, category=cls.cat, is_available=True)
        for i in range(4):
            ProductImage.objects.create(product=cls.multi, printify_src="https://x/%d.jpg" % i,
                                        is_default=(i == 0), sort_order=i)
        Variation.objects.create(product=cls.multi, variation_category="color", variation_value="Black", is_active=True)
        Variation.objects.create(product=cls.multi, variation_category="color", variation_value="Blue", is_active=True)
        Variation.objects.create(product=cls.multi, variation_category="size", variation_value="M", is_active=True)
        # single-image product, no variants
        cls.single = Product.objects.create(product_name="Plain Tee", slug="plain-tee-66",
                                            price=20, stock=5, category=cls.cat, is_available=True)
        ProductImage.objects.create(product=cls.single, printify_src="https://x/s.jpg", is_default=True)

    def setUp(self):
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)

    # -- THE FIX: CSS regression guard ---------------------------------------
    def test_pcard_carousel_is_transform_based_with_static_images(self):
        # Phase 75 replaced the scroll-snap carousel with a transform-based one. The critical
        # guarantee is that the slide IMAGE flows in the track (static), not position:absolute
        # (which stacked every slide so the visible image never changed).
        css = CSS.read_text(encoding="utf-8").replace(" ", "")
        self.assertIn(".pcard-slideimg{position:static!important", css)
        self.assertNotIn("scroll-snap-align:center", css,
                         "regression: center alignment pinned the track to scrollLeft 0")

    # -- gallery markup -------------------------------------------------------
    def test_multi_image_renders_scrollable_track(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-card-gallery", html)
        self.assertIn("pcard-track", html)
        self.assertIn('class="pcard-slide"', html)
        self.assertIn("data-card-next", html)
        self.assertIn("data-card-prev", html)
        self.assertIn("pcard-dot", html)

    def test_nav_controls_have_aria_labels(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("Previous image", html)
        self.assertIn("Next image", html)

    def test_single_image_has_no_gallery_controls(self):
        # store grid: the single-image product must not get a carousel
        html = self.client.get(reverse("store") + "?keyword=Plain Tee").content.decode()
        self.assertNotIn("data-card-gallery", html)

    # -- premium card features ------------------------------------------------
    def test_card_swatches_render(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("card-variants", html)
        self.assertIn("cv-dot", html)        # colour dots
        self.assertIn("cv-size", html)       # size pills

    def test_trust_panel_present(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("store-trust", html)
        self.assertIn("Made on demand", html)
        self.assertIn("Secure checkout", html)

    def test_card_variants_no_n_plus_1(self):
        resp = self.client.get(reverse("store"))
        products = list(resp.context["products"])
        with self.assertNumQueries(0):       # variation_set is prefetched
            for p in products:
                _ = p.card_variants()

    def test_card_variants_data(self):
        cv = self.multi.card_variants()
        self.assertEqual(set(c.lower() for c in cv["colors"]), {"black", "blue"})
        self.assertEqual([s.lower() for s in cv["sizes"]], ["m"])
        self.assertEqual(self.single.card_variants(), {})   # no variants -> empty

    # -- regressions ----------------------------------------------------------
    def test_quick_view_and_wishlist_present(self):
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("data-quick-view", html)
        self.assertIn("data-wishlist-toggle", html)

    def test_store_filters_still_work(self):
        # a colour filter still narrows results (uses the existing facet pipeline)
        r = self.client.get(reverse("store") + "?color=black")
        self.assertEqual(r.status_code, 200)
        names = {p.product_name for p in r.context["products"]}
        self.assertIn("Gallery Tee", names)
        self.assertNotIn("Plain Tee", names)

    def test_i18n(self):
        from django.utils import translation
        with translation.override("it"):
            self.assertEqual(translation.gettext("Available options"), "Opzioni disponibili")
            self.assertNotEqual(translation.gettext("Made on demand"), "Made on demand")  # translated
        with translation.override("fr"):
            self.assertEqual(translation.gettext("Secure checkout"), "Paiement sécurisé")
            self.assertEqual(translation.gettext("Available options"), "Options disponibles")
