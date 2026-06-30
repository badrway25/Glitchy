"""Phase 63: wishlist facets + quick actions + ownership + portal intelligence.

Builds real products (on-sale, multi-image, with colour/size variations) so the facet
filters can be exercised against actual data. No real PII.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from store.models import Category, Product, ProductImage, Variation
from wishlist.models import WishlistItem


def _user(email, username):
    u = Account.objects.create_user(first_name="QA", last_name="T", username=username,
                                    email=email, password="x-test-pass")
    u.is_active = True
    u.save()
    return u


def _product(name, slug, price, cat, *, compare=None, stock=5):
    return Product.objects.create(product_name=name, slug=slug, price=price, stock=stock,
                                  category=cat, compare_at_price=compare, is_available=True)


class Phase63WishlistFacetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")
        cls.cat2 = Category.objects.create(category_name="Hoodies", slug="hoodies")
        cls.alice = _user("alice63@example.com", "alice63")
        cls.bob = _user("bob63@example.com", "bob63")

        cls.p_sale = _product("Sale Tee", "sale-tee", 20, cls.cat, compare=40)   # on sale
        cls.p_multi = _product("Gallery Tee", "gallery-tee", 30, cls.cat)         # multi-image
        for i in range(3):
            ProductImage.objects.create(product=cls.p_multi, printify_src="https://x/%d.jpg" % i,
                                        is_default=(i == 0), sort_order=i)
        cls.p_var = _product("Color Tee", "color-tee", 50, cls.cat)               # colour+size
        Variation.objects.create(product=cls.p_var, variation_category="color", variation_value="Red", is_active=True)
        Variation.objects.create(product=cls.p_var, variation_category="size", variation_value="M", is_active=True)
        cls.p_plain = _product("Plain Hoodie", "plain-hoodie", 80, cls.cat2)      # no facets

        for p in [cls.p_sale, cls.p_multi, cls.p_var, cls.p_plain]:
            WishlistItem.objects.create(user=cls.alice, product=p)
        WishlistItem.objects.create(user=cls.bob, product=cls.p_plain)            # bob's own

    def setUp(self):
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)
        self.client.force_login(self.alice)

    def _names(self, resp):
        return {it.product.product_name for it in resp.context["wishlist_items"]}

    # -- facets ---------------------------------------------------------------
    def test_render_with_facets(self):
        html = self.client.get(reverse("wishlist:saved")).content.decode()
        self.assertIn("portal-chip", html)
        self.assertIn("wf-facet", html)
        self.assertIn("portal-result-count", html)

    def test_facet_sale(self):
        r = self.client.get(reverse("wishlist:saved") + "?sale=1")
        self.assertEqual(self._names(r), {"Sale Tee"})

    def test_facet_multi_image(self):
        r = self.client.get(reverse("wishlist:saved") + "?multi=1")
        self.assertEqual(self._names(r), {"Gallery Tee"})

    def test_facet_color(self):
        r = self.client.get(reverse("wishlist:saved") + "?color=red")
        self.assertEqual(self._names(r), {"Color Tee"})

    def test_facet_size(self):
        r = self.client.get(reverse("wishlist:saved") + "?size=m")
        self.assertEqual(self._names(r), {"Color Tee"})

    def test_facet_category(self):
        r = self.client.get(reverse("wishlist:saved") + "?category=hoodies")
        self.assertEqual(self._names(r), {"Plain Hoodie"})

    def test_facet_price_range(self):
        r = self.client.get(reverse("wishlist:saved") + "?min_price=45")
        self.assertEqual(self._names(r), {"Color Tee", "Plain Hoodie"})

    def test_facet_counts_present(self):
        ctx = self.client.get(reverse("wishlist:saved")).context
        self.assertEqual(ctx["facets"]["sale_count"], 1)
        self.assertEqual(ctx["facets"]["multi_count"], 1)
        self.assertTrue(any(c["slug"] == "tees" for c in ctx["facets"]["categories"]))

    def test_chips_and_clear(self):
        html = self.client.get(reverse("wishlist:saved") + "?sale=1").content.decode()
        self.assertIn("active-chip", html)
        self.assertIn("Clear all", html)

    def test_querystring_preserved(self):
        ctx = self.client.get(reverse("wishlist:saved") + "?sale=1&sort=price_low").context
        self.assertIn("sale=1", ctx["querystring"])
        self.assertIn("sort=price_low", ctx["querystring"])

    def test_invalid_inputs_safe(self):
        r = self.client.get(reverse("wishlist:saved") + "?min_price=abc&max_price=-9&color=" + "x" * 80)
        self.assertEqual(r.status_code, 200)

    # -- quick actions / card -------------------------------------------------
    def test_card_quick_actions_and_sale(self):
        html = self.client.get(reverse("wishlist:saved")).content.decode()
        self.assertIn("data-quick-view", html)        # quick view
        self.assertIn("data-wishlist-toggle", html)   # remove
        self.assertIn("saved-sale", html)             # sale badge for p_sale
        self.assertIn("pcard-gallery", html)          # multi-image gallery reuse

    # -- performance ----------------------------------------------------------
    def test_no_n_plus_1_on_gallery(self):
        # cover_image() reads the prefetched gallery -> no per-card query
        resp = self.client.get(reverse("wishlist:saved"))
        items = list(resp.context["wishlist_items"])
        with self.assertNumQueries(0):
            for it in items:
                _ = it.product.cover_image()

    # -- ownership / security -------------------------------------------------
    def test_wishlist_scoped_to_user(self):
        self.client.force_login(self.bob)
        names = self._names(self.client.get(reverse("wishlist:saved")))
        self.assertEqual(names, {"Plain Hoodie"})       # only bob's own item

    def test_facet_does_not_leak_other_users(self):
        # bob filters by a category only alice has populated heavily -> still only his
        self.client.force_login(self.bob)
        r = self.client.get(reverse("wishlist:saved") + "?sale=1")
        self.assertEqual(self._names(r), set())          # bob has no sale item

    # -- portal nav badges + activity ----------------------------------------
    def test_sidebar_wishlist_badge(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("acc-badge", html)                 # alice has wishlist items -> badge

    def test_activity_includes_wishlist(self):
        ctx = self.client.get(reverse("dashboard")).context
        titles = [a["title"] for a in ctx["activity"]]
        self.assertIn("Saved to wishlist", titles)

    # -- legacy premium + regressions ----------------------------------------
    def test_login_register_premium_with_toggle(self):
        self.client.logout()
        for name in ["login", "register"]:
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn("auth-card", html)
            self.assertIn("data-pw-toggle", html)
            self.assertEqual(html.count("<form"), html.count("</form>"))   # no broken/nested forms

    def test_checkout_redirect_regression(self):
        self.client.logout()
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")

    def test_i18n_facets(self):
        # verify the compiled catalog (wishlist is outside i18n_patterns)
        from django.utils import translation
        with translation.override("it"):
            self.assertEqual(translation.gettext("Recently saved"), "Salvati di recente")
            self.assertEqual(translation.gettext("Multi-image"), "Più immagini")
        with translation.override("fr"):
            self.assertEqual(translation.gettext("On sale"), "En solde")
            self.assertEqual(translation.gettext("Apply filters"), "Appliquer les filtres")
