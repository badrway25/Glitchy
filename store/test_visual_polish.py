"""Phase 40: logo branding, rating component, no-leak visual polish."""
from django.test import TestCase
from django.urls import reverse

from category.models import Category
from store.models import Product, ReviewRating
from accounts.models import Account


def _product(name="Tee", **kw):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description="x",
             price=20, stock=5, category=cat, is_available=True)
    d.update(kw)
    return Product.objects.create(**d)


class LogoBrandingTests(TestCase):
    def test_navbar_uses_real_logo_image(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("logo-glitchy-nav.png", html)          # dark (light theme)
        self.assertIn("logo-glitchy-nav-light.png", html)    # white (dark theme)
        self.assertIn('class="navbar-brand brand-logo"', html)

    def test_footer_uses_real_logo_image(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("logo-glitchy-footer-light.png", html)

    def test_old_text_brandmark_span_removed(self):
        html = self.client.get(reverse("home")).content.decode()
        # the old decorative <span class="brand-mark"> text-logo is gone
        self.assertNotIn('class="navbar-brand brand-word"', html)
        self.assertNotIn('class="footer-brand brand-word"', html)

    def test_logo_has_accessible_alt(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("fashion store", html)   # alt text on the brand image


class CardRatingTests(TestCase):
    def setUp(self):
        self.u = Account.objects.create_user(email="r@x.com", username="r", first_name="R",
                                             last_name="R", password="pw12345!")

    def test_card_rating_hidden_without_reviews(self):
        p = _product("NoReviews")
        # render via the store page (uses _product_card)
        html = self.client.get(reverse("store")).content.decode()
        self.assertNotIn("card-rating", html)   # no fake rating shown

    def test_card_rating_shown_with_real_review(self):
        p = _product("Reviewed")
        ReviewRating.objects.create(product=p, user=self.u, rating=4, subject="ok",
                                    review="good", status=True)
        html = self.client.get(reverse("store")).content.decode()
        self.assertIn("card-rating", html)
        self.assertIn("rating-stars-fill", html)
