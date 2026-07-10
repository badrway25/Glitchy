"""PDP premium phase — colour-driven gallery + structured description (integration).

Covers the view context and rendered markup: the persisted colour→image map is
exposed as a json_script, thumbs carry data-image-id/data-colors, the description
renders as Overview / Highlights / Care sections, and everything degrades
gracefully when the data is absent (no map rows, unstructured text).
"""
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from category.models import Category
from store.models import Product, ProductColorImage, ProductImage, Variation

TINY_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
            b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

MEDIA = tempfile.mkdtemp(prefix="pdp-premium-test-")

STRUCTURED_DESC = (
    "A quiet, comfortable tee for slow mornings and late-night reads. "
    "Soft against the skin, it keeps its shape through many seasons and "
    "pairs with everything you already own — a small, wearable pause "
    "in a loud day, cut with room to breathe, made to be worn often, "
    "and finished with the kind of detail you only notice the third time.\n"
    "\n"
    "Product features\n"
    "- 100% ring-spun cotton\n"
    "- Tubular knit construction\n"
    "\n"
    "Care instructions\n"
    "- Machine wash: cold\n"
    "- Do not bleach"
)


def _make_product(slug, description=""):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    return Product.objects.create(
        product_name=slug.replace("-", " ").title(), slug=slug,
        description=description, price=25, stock=5, category=cat,
    )


def _gallery_image(product, name, variant_ids="", sort_order=0, is_default=False):
    img = ProductImage(product=product, printify_variant_ids=variant_ids,
                       printify_src=f"https://images.example/{name}",
                       sort_order=sort_order, is_default=is_default)
    img.image.save(name, ContentFile(TINY_GIF), save=True)
    return img


@override_settings(MEDIA_ROOT=MEDIA)
class PdpColorGalleryTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.product = _make_product("mars-walker-tee", STRUCTURED_DESC)
        Variation.objects.create(product=self.product, variation_category="color",
                                 variation_value="Black")
        Variation.objects.create(product=self.product, variation_category="color",
                                 variation_value="White")
        self.img_black = _gallery_image(self.product, "black.gif", "1,2", 0, is_default=True)
        self.img_white = _gallery_image(self.product, "white.gif", "3,4", 1)
        ProductColorImage.objects.create(
            product=self.product, color_value="black",
            image_ids=str(self.img_black.id), primary_image=self.img_black,
            source=ProductColorImage.SOURCE_DETERMINISTIC, confidence=1.0)
        ProductColorImage.objects.create(
            product=self.product, color_value="white",
            image_ids=str(self.img_white.id), primary_image=self.img_white,
            source=ProductColorImage.SOURCE_DETERMINISTIC, confidence=1.0)

    def _get(self):
        return self.client.get(self.product.get_url())

    def test_json_map_rendered(self):
        resp = self._get()
        self.assertContains(resp, 'id="pdpColorImages"')
        self.assertContains(resp, '"black"')
        self.assertContains(resp, '"primary"')
        self.assertContains(resp, self.img_white.image.url)

    def test_thumbs_carry_image_id_and_colors(self):
        resp = self._get()
        self.assertContains(resp, 'data-image-id="%d"' % self.img_black.id)
        self.assertContains(resp, 'data-colors="black"')
        self.assertContains(resp, 'data-colors="white"')

    def test_pdp_premium_js_loaded(self):
        self.assertContains(self._get(), "js/pdp-premium.js")

    def test_product_without_map_renders_fine(self):
        bare = _make_product("bare-tee", "Just a plain description.")
        resp = self.client.get(bare.get_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="pdpColorImages"')

    def test_map_row_pointing_at_deleted_image_is_skipped(self):
        ProductColorImage.objects.filter(product=self.product, color_value="white") \
            .update(image_ids="99999", primary_image=None)
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        # white entry dropped from the JSON map (no resolvable images)
        import json as jsonlib
        import re as relib
        m = relib.search(rb'<script id="pdpColorImages"[^>]*>(.*?)</script>',
                         resp.content, relib.S)
        data = jsonlib.loads(m.group(1))
        self.assertNotIn("white", data)
        self.assertIn("black", data)


class PdpDescriptionSectionTests(TestCase):
    def test_structured_description_renders_sections(self):
        p = _make_product("sections-tee", STRUCTURED_DESC)
        resp = self.client.get(p.get_url())
        self.assertContains(resp, 'class="pdp-highlights"')
        self.assertContains(resp, "100% ring-spun cotton")
        self.assertContains(resp, '<details class="pdp-details">')
        self.assertContains(resp, "Machine wash: cold")
        self.assertContains(resp, "Care instructions")
        # the intro stays visible and the raw heading lines are consumed
        self.assertContains(resp, "quiet, comfortable tee")
        self.assertNotContains(resp, "Product features")

    def test_long_overview_gets_read_more(self):
        p = _make_product("long-tee", STRUCTURED_DESC)
        resp = self.client.get(p.get_url())
        self.assertContains(resp, "data-overview-toggle")
        self.assertContains(resp, "is-clamped")

    def test_short_overview_has_no_toggle(self):
        p = _make_product("short-tee", "Short and sweet.\n- 100% cotton")
        resp = self.client.get(p.get_url())
        self.assertNotContains(resp, "data-overview-toggle")

    def test_all_highlights_render_without_cap(self):
        bullets = "\n".join(f"- Feature number {i} of the garment" for i in range(1, 9))
        p = _make_product("many-bullets-tee", f"Intro.\n{bullets}")
        resp = self.client.get(p.get_url())
        for i in range(1, 9):        # review regression: bullets 7+ used to vanish
            self.assertContains(resp, f"Feature number {i} of the garment")

    def test_unstructured_description_falls_back(self):
        p = _make_product("plain-tee", "One honest paragraph, nothing else.")
        resp = self.client.get(p.get_url())
        self.assertContains(resp, "One honest paragraph, nothing else.")
        self.assertNotContains(resp, 'class="pdp-highlights"')
        self.assertNotContains(resp, '<details class="pdp-details">')

    def test_no_html_injection_via_description(self):
        p = _make_product("evil-tee", "Intro.\n- <script>alert(1)</script> cotton")
        resp = self.client.get(p.get_url())
        self.assertNotContains(resp, "<script>alert(1)</script>", html=False)
        self.assertContains(resp, "&lt;script&gt;")
