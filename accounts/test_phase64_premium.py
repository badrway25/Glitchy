"""Phase 64: ultra-premium page detail + motion polish render/regression tests.

Verifies the premium shell (lux-head/summary/empty), the split auth layout, the grouped
address form, the dashboard hero + count-up, and that nothing regressed (forms balanced,
CSRF present, no nested forms, checkout redirect, wishlist facets still filter). No PII.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from store.models import Category, Product
from wishlist.models import WishlistItem


def _user(email, username):
    u = Account.objects.create_user(first_name="QA", last_name="T", username=username,
                                    email=email, password="x-test-pass")
    u.is_active = True
    u.save()
    return u


class Phase64PremiumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")
        cls.u = _user("p64@example.com", "p64user")
        cls.p1 = Product.objects.create(product_name="Sale Tee", slug="sale-tee", price=20,
                                        stock=5, category=cls.cat, compare_at_price=40, is_available=True)
        WishlistItem.objects.create(user=cls.u, product=cls.p1)

    def setUp(self):
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)

    @staticmethod
    def _balanced(html):
        return html.count("<form") == html.count("</form>")

    # -- shared shell / motion ------------------------------------------------
    def test_motion_js_loaded(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("page-polish-motion.js", html)

    # -- wishlist -------------------------------------------------------------
    def test_wishlist_premium_shell(self):
        self.client.force_login(self.u)
        html = self.client.get(reverse("wishlist:saved")).content.decode()
        self.assertIn("lux-head", html)
        self.assertIn("lux-summary", html)
        self.assertIn("data-countup", html)        # saved count animates
        self.assertIn("data-reveal-stagger", html)  # card grid stagger

    def test_wishlist_no_results_luxury(self):
        self.client.force_login(self.u)
        html = self.client.get(reverse("wishlist:saved") + "?min_price=999999").content.decode()
        self.assertIn("lux-empty", html)
        self.assertIn("Clear filters", html)

    def test_wishlist_facets_still_filter(self):
        self.client.force_login(self.u)
        r = self.client.get(reverse("wishlist:saved") + "?sale=1")
        names = {it.product.product_name for it in r.context["wishlist_items"]}
        self.assertEqual(names, {"Sale Tee"})

    # -- login / register split ----------------------------------------------
    def test_login_split_premium(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("auth-split", html)
        self.assertIn("auth-side", html)
        self.assertIn("data-pw-toggle", html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertTrue(self._balanced(html))

    def test_register_split_with_benefits(self):
        html = self.client.get(reverse("register")).content.decode()
        self.assertIn("auth-split", html)
        self.assertEqual(html.count("auth-benefit-ic"), 4)   # 4 benefit cards
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertTrue(self._balanced(html))                # forms open==close (no broken/nested)
        self.assertIn('class="auth-form"', html)             # the register form is present

    # -- dashboard ------------------------------------------------------------
    def test_dashboard_premium_hero(self):
        self.client.force_login(self.u)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("lux-head", html)
        self.assertIn("lux-eyebrow", html)
        self.assertIn("data-countup", html)
        self.assertIn("data-reveal-stagger", html)

    # -- address form ---------------------------------------------------------
    def test_address_form_grouped_premium(self):
        self.client.force_login(self.u)
        html = self.client.get(reverse("address_create")).content.decode()
        self.assertIn("addr-section", html)
        self.assertIn("addr-switch", html)                   # elegant default toggle
        self.assertIn("Shipping address", html)              # grouped section
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn('class="addr-form"', html)             # the address form is present
        self.assertTrue(self._balanced(html))                # forms open==close (no broken/nested)

    # -- store ----------------------------------------------------------------
    def test_store_renders(self):
        r = self.client.get(reverse("store"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("data-reveal", r.content.decode())     # store header reveal

    # -- i18n + regressions ---------------------------------------------------
    def test_i18n_new_strings(self):
        from django.utils import translation
        with translation.override("it"):
            self.assertEqual(translation.gettext("Your collection"), "La tua collezione")
            self.assertEqual(translation.gettext("Shipping address"), "Indirizzo di spedizione")
        with translation.override("fr"):
            self.assertEqual(translation.gettext("Member benefits"), "Avantages membres")

    def test_checkout_redirect_regression(self):
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")
