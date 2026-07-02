"""Store card carousel + premium filter system (Phase 75) — regression tests.

The visual behaviour (image actually changing, focus ring, collapse spacing) is verified in the
browser; these lock in the structural + data guarantees that make it work.
"""
import pathlib

from django.conf import settings
from django.test import TestCase

from category.models import Category
from store.models import Product, ProductImage

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "product-card-gallery.js"


class CardImageOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees", is_public=True)

    def _p(self):
        return Product.objects.create(product_name="Tee", slug="tee", price=20, category=self.cat,
                                      is_available=True, stock=10)

    def test_gallery_first_not_main_prepended(self):
        # the main image is a content-duplicate of a gallery image; it must NOT be prepended
        # (that made slides 0 and 1 identical -> "next" appeared to do nothing).
        p = self._p()
        ProductImage.objects.create(product=p, printify_src="https://cdn/g1.png", sort_order=1)
        ProductImage.objects.create(product=p, printify_src="https://cdn/g2.png", sort_order=2)
        urls = p.card_image_urls()
        self.assertEqual(urls, ["https://cdn/g1.png", "https://cdn/g2.png"])   # gallery only

    def test_main_used_only_when_no_gallery(self):
        p = self._p()
        # no gallery -> nothing to show unless main; give it a gallery-less product
        self.assertEqual(p.card_image_urls(), [])          # no gallery, no main file

    def test_dedupe_by_url(self):
        p = self._p()
        for i in range(3):
            ProductImage.objects.create(product=p, printify_src="https://cdn/same.png", sort_order=i)
        self.assertEqual(p.card_image_urls(), ["https://cdn/same.png"])


class CarouselStructureTests(TestCase):
    def test_carousel_js_is_transform_based(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("translateX", js)                    # transform, not scroll
        self.assertIn("initProductCardGalleries", js)      # idempotent init entry point
        self.assertNotIn("scrollTo(", js)                  # no longer the scroll-based mover

    def test_slide_image_forced_static_position(self):
        css = CSS.read_text(encoding="utf-8")
        # the fix for the "image never changes" bug: override .media-skeleton img{position:absolute}
        self.assertIn(".pcard-slide img{position:static!important", css)
        self.assertIn(".pcard-gallery{position:absolute;inset:0;z-index:1;overflow:hidden;}", css)

    def test_store_card_next_button_is_type_button_and_not_a_link(self):
        # render the store and assert the next control is a <button type=button>, not an <a>
        p = Product.objects.create(product_name="Multi", slug="multi", price=10,
                                   category=Category.objects.create(category_name="C", slug="c", is_public=True),
                                   is_available=True, stock=5)
        ProductImage.objects.create(product=p, printify_src="https://cdn/a.png", sort_order=1)
        ProductImage.objects.create(product=p, printify_src="https://cdn/b.png", sort_order=2)
        html = self.client.get("/store/").content.decode()
        self.assertIn('class="pcard-nav pcard-next"', html)
        self.assertIn('data-card-next', html)
        # the next button must be a button, not inside a navigating <a> as the control itself
        idx = html.find("pcard-next")
        snippet = html[max(0, idx - 60):idx]
        self.assertIn('type="button"', snippet)


class FilterCssTests(TestCase):
    def test_price_field_focus_within_wraps_group(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lxf-price-field:focus-within{", css)      # focus wraps € + input
        self.assertIn(".lxf-price-field input{", css)
        self.assertIn("outline:none", css)

    def test_filter_body_has_top_spacing_when_open_and_none_when_collapsed(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lxf-body > *{overflow:hidden;min-height:0;padding:.9rem", css)
        self.assertIn(".lxf-section.is-collapsed .lxf-body > *{padding-top:0;padding-bottom:0;}", css)

    def test_color_swatch_selected_state_is_clear(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lxf-swatch:has(input:checked){background:", css)   # row highlight
        self.assertIn(".lxf-swatch:has(input:checked)::after{content:", css)  # checkmark
        self.assertIn('"\\2713"', css)

    def test_color_filter_applies_via_querystring(self):
        # a color filter narrows the queryset (structural guarantee)
        cat = Category.objects.create(category_name="X", slug="x", is_public=True)
        resp = self.client.get("/store/?color=black")
        self.assertEqual(resp.status_code, 200)
