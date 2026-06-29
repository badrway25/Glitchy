"""Phase 61: ultra-premium navbar auth buttons + product card image carousel.

Verifies the navbar Login/Register button system, the store product-card carousel
(multi-image render, single-image fallback, lazy/alt, 5-image cap, prefetch/no N+1),
and that Phase 57/60 behaviour (language switcher, checkout redirect) still holds.
No real data; gallery rows use printify_src (no image files needed).
"""
import pathlib

from django.conf import settings
from django.test import TestCase

from category.models import Category
from store.models import Product, ProductImage

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
NAVBAR = pathlib.Path(settings.BASE_DIR) / "templates" / "includes" / "navbar.html"
STORE_VIEW = pathlib.Path(settings.BASE_DIR) / "store" / "views.py"


class Phase61Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")
        cls.multi = cls._product("Multi Shot", "multi", price=20)
        for i in range(7):  # 7 images -> carousel must cap at 5
            ProductImage.objects.create(product=cls.multi, sort_order=i,
                                        printify_src=f"https://img.example/multi-{i}.jpg")
        cls.single = cls._product("Single Shot", "single", price=15)
        ProductImage.objects.create(product=cls.single, sort_order=0,
                                    printify_src="https://img.example/single-0.jpg")

    @staticmethod
    def _product(name, slug, *, price):
        return Product.objects.create(product_name=name, slug=slug, price=price,
                                      stock=9999, category=Category.objects.get(slug="tees"))

    def _store(self):
        return self.client.get("/store/").content.decode()

    # -- navbar auth ----------------------------------------------------------
    def test_navbar_auth_buttons(self):
        html = self.client.get("/").content.decode()
        self.assertIn("nav-auth", html)
        self.assertIn("btn-auth btn-auth-soft", html)   # Login
        self.assertIn("btn-auth btn-auth-gold", html)   # Register (gold)
        self.assertNotIn("btn btn-outline-primary", html.split("nav-auth")[1][:200])

    def test_register_gold_and_equal_size_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".btn-auth-gold", css)
        self.assertIn("--btn-elegant", css)              # gold token used
        self.assertIn(".btn-auth{", css.replace(" ", ""))  # shared sizing class

    # -- product card carousel ------------------------------------------------
    def test_multi_image_renders_carousel(self):
        html = self._store()
        self.assertIn("data-card-gallery", html)
        self.assertIn("pcard-track", html)
        self.assertIn("pcard-prev", html)
        self.assertIn("pcard-next", html)

    def test_carousel_caps_at_five_images(self):
        html = self._store()
        # the multi product has 7 images; only 5 slides + 5 dots may render
        self.assertEqual(html.count('class="pcard-slide"'), 5)
        self.assertEqual(html.count('<span class="pcard-dot'), 5)  # span dots, not the container

    def test_single_image_card_has_no_carousel_controls(self):
        # In the grid, only the multi-image product gets a carousel; the
        # single-image product falls back to the plain skeleton image (no controls).
        html = self._store()
        self.assertEqual(html.count("data-card-gallery"), 1)   # only 'multi'
        self.assertIn("data-skeleton", html)                   # 'single' fallback present

    def test_gallery_images_lazy_and_alt(self):
        import re
        html = self._store()
        imgs = re.findall(r"<img[^>]*>", html.split("pcard-track")[1].split("</div>")[0])
        self.assertTrue(imgs)
        for tag in imgs:
            self.assertRegex(tag, r'alt="[^"]+"')
        # first slide eager, later lazy
        self.assertIn('loading="eager"', html)
        self.assertIn('loading="lazy"', html)

    def test_placeholder_fallback_when_no_gallery(self):
        Product.objects.create(product_name="No Img", slug="no-img", price=9, stock=5,
                               category=self.cat)
        html = self._store()
        self.assertIn("placeholder.png", html)

    # -- backend: prefetch / no N+1 ------------------------------------------
    def test_store_prefetches_gallery_source(self):
        self.assertIn('prefetch_related("gallery")', STORE_VIEW.read_text(encoding="utf-8"))

    def test_store_gallery_is_prefetched_no_n_plus_1(self):
        # add more multi-image products, then prove the gallery is prefetched:
        # iterating every product's gallery must hit the DB ZERO times.
        for n in range(5):
            p = self._product(f"Extra {n}", f"extra-{n}", price=12)
            for i in range(3):
                ProductImage.objects.create(product=p, sort_order=i,
                                            printify_src=f"https://img.example/e{n}-{i}.jpg")
        resp = self.client.get("/store/")
        products = list(resp.context["products"])
        self.assertTrue(products)
        with self.assertNumQueries(0):
            for p in products:
                list(p.gallery.all())

    # -- regressions ----------------------------------------------------------
    def test_quick_view_and_wishlist_present(self):
        html = self._store()
        self.assertIn("data-quick-view", html)
        self.assertIn("data-wishlist-toggle", html)

    def test_checkout_redirect_still_ok(self):
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")

    def test_language_switcher_no_codes(self):
        html = self.client.get("/").content.decode()
        self.assertIn("lang-switcher", html)
        self.assertNotIn("(EN)", html)
        self.assertNotIn("lang-code", html)

    def test_carousel_strings_localized(self):
        it = self.client.get("/it/store/").content.decode()
        self.assertIn("Immagine successiva", it)
        fr = self.client.get("/fr/store/").content.decode()
        self.assertIn("Image suivante", fr)
