"""Store visual interaction fixes (Phase 74) — regression tests.

Covers: card carousel image sourcing (dedup + Printify remote fallback), cover/hover fallback,
Glitchy favicon wiring, and the discreet per-visitor shipping-country detection + valid quote.
"""
import pathlib

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from category.models import Category
from store.models import Product, ProductImage


class CardImageUrlsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees", is_public=True)

    def _p(self, name):
        return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                      price=20, category=self.cat, is_available=True, stock=10)

    def test_gallery_images_use_remote_src_when_no_local_file(self):
        # a synced Printify image with only a remote src (download failed) must still resolve
        p = self._p("Remote Tee")
        ProductImage.objects.create(product=p, printify_src="https://cdn/x1.png", sort_order=1)
        ProductImage.objects.create(product=p, printify_src="https://cdn/x2.png", sort_order=2)
        urls = p.card_image_urls()
        self.assertEqual(urls, ["https://cdn/x1.png", "https://cdn/x2.png"])

    def test_card_image_urls_dedupe(self):
        # duplicate Printify mockup srcs collapse (so the carousel shows DISTINCT photos)
        p = self._p("Dup Tee")
        for i in range(3):
            ProductImage.objects.create(product=p, printify_src="https://cdn/same.png", sort_order=i)
        self.assertEqual(p.card_image_urls(), ["https://cdn/same.png"])   # 1 distinct

    def test_cover_image_falls_back_to_printify_src(self):
        p = self._p("Cover Tee")
        ProductImage.objects.create(product=p, printify_src="https://cdn/cover.png")
        self.assertEqual(p.cover_image(), "https://cdn/cover.png")

    def test_single_image_product_has_no_multi_slide(self):
        p = self._p("Single Tee")
        ProductImage.objects.create(product=p, printify_src="https://cdn/only.png")
        self.assertEqual(len(p.card_image_urls()), 1)

    def test_store_card_renders_carousel_for_multi_image(self):
        p = self._p("Carousel Tee")
        ProductImage.objects.create(product=p, printify_src="https://cdn/a.png", sort_order=1)
        ProductImage.objects.create(product=p, printify_src="https://cdn/b.png", sort_order=2)
        html = self.client.get("/store/").content.decode()
        self.assertIn("data-card-gallery", html)
        self.assertIn("data-card-next", html)


class FaviconTests(TestCase):
    def test_base_template_links_glitchy_favicon(self):
        html = self.client.get("/").content.decode()
        self.assertIn("images/favicon.ico", html)
        self.assertIn("apple-touch-icon", html)
        self.assertIn('name="theme-color"', html)

    def test_favicon_asset_regenerated_multisize(self):
        ico = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "images" / "favicon.ico"
        self.assertTrue(ico.exists())
        # the stale 16x16 favicon was ~1.1KB; the Glitchy multi-size one is larger
        self.assertGreater(ico.stat().st_size, 3000)
        for png in ("favicon-32.png", "favicon-16.png", "apple-touch-icon.png"):
            self.assertTrue((ico.parent / png).exists(), "missing %s" % png)


@override_settings(SHIPPING_DEFAULT_COUNTRY="IT")
class ShippingCountryTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, cf=None):
        from django.contrib.sessions.backends.db import SessionStore
        meta = {"HTTP_CF_IPCOUNTRY": cf} if cf else {}
        r = self.rf.get("/", **meta)
        r.session = SessionStore()
        return r

    def test_cdn_header_detected_and_cached(self):
        from shipping.geo import detect_country, AUTO_KEY
        r = self._req(cf="FR")
        self.assertEqual(detect_country(r), "FR")
        self.assertEqual(r.session.get(AUTO_KEY), "FR")     # cached (one-time, discreet)

    def test_default_when_no_signal(self):
        from shipping.geo import detect_country
        self.assertEqual(detect_country(self._req()), "IT")

    def test_manual_override_wins(self):
        from shipping.geo import detect_country, set_manual_country
        r = self._req(cf="US")
        set_manual_country(r, "DE")
        self.assertEqual(detect_country(r), "DE")

    def test_per_country_quote_is_valid(self):
        from shipping.services import fallback_quote
        it = fallback_quote("IT", total_quantity=1, subtotal=25.0)
        us = fallback_quote("US", total_quantity=1, subtotal=25.0)
        self.assertNotEqual(it.cost, us.cost)               # real per-country rates
        self.assertTrue(it.eta_label and us.eta_label)
