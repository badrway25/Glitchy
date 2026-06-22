"""Phase 19 tests: autocomplete, verified reviews, rating summary, FAQ JSON-LD."""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from category.models import Category
from orders.models import Order, OrderProduct
from store.models import GeneralFAQ, Product, ReviewRating

User = get_user_model()


def _cat():
    return Category.objects.get_or_create(category_name="Tees", slug="tees")[0]


def _product(slug="p1", name="Blue Tee"):
    return Product.objects.create(product_name=name, slug=slug, price=20, category=_cat(),
                                  is_available=True, stock=5)


def _user(email):
    u = User.objects.create_user(email=email, first_name="A", last_name="B",
                                 username=email.split("@")[0], password="pw12345!")
    u.is_active = True
    u.save()
    return u


class AutocompleteTests(TestCase):
    def setUp(self):
        self.c = Client()
        _product("blue-tee", "Blue Tee")
        _product("red-tee", "Red Tee")

    def test_valid_query_returns_results(self):
        r = self.c.get(reverse("autocomplete"), {"q": "tee"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()["results"]), 1)

    def test_empty_query_no_results_no_500(self):
        r = self.c.get(reverse("autocomplete"), {"q": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"], [])

    def test_weird_query_no_500(self):
        r = self.c.get(reverse("autocomplete"), {"q": "<script>alert(1)</script>"})
        self.assertEqual(r.status_code, 200)

    def test_result_limit(self):
        for i in range(10):
            _product(f"tee-{i}", f"Tee {i}")
        r = self.c.get(reverse("autocomplete"), {"q": "tee"})
        self.assertLessEqual(len(r.json()["results"]), 6)


class VerifiedReviewTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.p = _product()
        self.buyer = _user("buyer@example.com")
        self.stranger = _user("stranger@example.com")

    def _order_for(self, user):
        o = Order.objects.create(user=user, first_name="A", last_name="B", phone="1",
                                 email=user.email, address_line_1="x", city="c", state="s",
                                 country="US", order_total=20, tax=2, ip="127.0.0.1",
                                 is_ordered=True, order_number="O1")
        OrderProduct.objects.create(order=o, user=user, product=self.p, quantity=1,
                                    product_price=20, ordered=True, payment=None)

    def test_verified_badge_only_for_buyer(self):
        self._order_for(self.buyer)
        ReviewRating.objects.create(product=self.p, user=self.buyer, subject="great",
                                    review="love it", rating=5, status=True)
        ReviewRating.objects.create(product=self.p, user=self.stranger, subject="meh",
                                    review="ok", rating=3, status=True)
        r = self.c.get(self.p.get_url())
        # exactly one verified badge (the buyer)
        self.assertContains(r, "Verified purchase", count=1)

    def test_summary_counts_only_approved(self):
        ReviewRating.objects.create(product=self.p, user=self.buyer, subject="a",
                                    review="a", rating=5, status=True)
        ReviewRating.objects.create(product=self.p, user=self.stranger, subject="b",
                                    review="b", rating=1, status=False)  # not approved
        r = self.c.get(self.p.get_url())
        self.assertEqual(r.context["review_count"], 1)
        self.assertEqual(r.context["review_avg"], 5.0)

    def test_aggregate_rating_only_with_reviews(self):
        # no reviews -> no AggregateRating in JSON-LD
        r = self.c.get(self.p.get_url())
        self.assertNotContains(r, "AggregateRating")
        ReviewRating.objects.create(product=self.p, user=self.buyer, subject="a",
                                    review="a", rating=4, status=True)
        r2 = self.c.get(self.p.get_url())
        self.assertContains(r2, "AggregateRating")


class FaqPageTests(TestCase):
    def setUp(self):
        self.c = Client()

    def test_faqpage_jsonld_only_with_real_faqs(self):
        r = self.c.get(reverse("faq"))
        self.assertNotContains(r, "FAQPage")  # none seeded in test DB
        GeneralFAQ.objects.create(category="shipping", question="Q1?", answer="A1.", is_active=True)
        r2 = self.c.get(reverse("faq"))
        self.assertContains(r2, "FAQPage")
        self.assertContains(r2, "Q1?")

    def test_faq_xss_escaped(self):
        GeneralFAQ.objects.create(category="support", question="<script>x</script>",
                                  answer="<b>bold</b>", is_active=True)
        r = self.c.get(reverse("faq"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<script>x</script>")


class AutocompleteSecurityTests(TestCase):
    def setUp(self):
        self.c = Client()

    def test_response_is_json_not_html(self):
        # A product whose name contains markup must be returned as JSON data,
        # never as an executable HTML document (so it can't run as script).
        _product("xss-tee", "<script>alert(1)</script> Tee")
        r = self.c.get(reverse("autocomplete"), {"q": "tee"})
        self.assertEqual(r["Content-Type"].split(";")[0], "application/json")
        # the raw markup is JSON-encoded data, not an HTML <script> element
        import json
        data = json.loads(r.content)
        names = [x["name"] for x in data["results"]]
        self.assertIn("<script>alert(1)</script> Tee", names)  # preserved as data
        # and the response is not served as text/html
        self.assertNotIn("text/html", r["Content-Type"])

    def test_very_long_query_no_500(self):
        r = self.c.get(reverse("autocomplete"), {"q": "a" * 5000})
        self.assertEqual(r.status_code, 200)


class RatingValidationTests(TestCase):
    """Phase 21: rating must be 1–5 at the form, model and DB level."""
    def setUp(self):
        self.p = _product()
        self.u = _user("rater@example.com")

    def test_form_rejects_out_of_range(self):
        from store.forms import ReviewForm
        for bad in (0, 6, -1, 7.5):
            form = ReviewForm(data={"subject": "x", "review": "y", "rating": bad})
            self.assertFalse(form.is_valid(), f"rating {bad} should be invalid")
            self.assertIn("rating", form.errors)

    def test_form_accepts_valid(self):
        from store.forms import ReviewForm
        for good in (1, 3, 5):
            form = ReviewForm(data={"subject": "x", "review": "y", "rating": good})
            self.assertTrue(form.is_valid(), f"rating {good} should be valid")

    def test_model_full_clean_rejects_out_of_range(self):
        from django.core.exceptions import ValidationError
        r = ReviewRating(product=self.p, user=self.u, subject="x", review="y", rating=6)
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_db_constraint_rejects_out_of_range(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReviewRating.objects.create(product=self.p, user=self.u,
                                            subject="x", review="y", rating=9)

    def test_db_accepts_valid(self):
        r = ReviewRating.objects.create(product=self.p, user=self.u,
                                        subject="x", review="y", rating=4)
        self.assertEqual(r.rating, 4)
