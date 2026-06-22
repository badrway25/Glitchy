"""Phase 23 tests: advanced shop filters, URL params, chips, no-results."""
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from category.models import Category
from store.models import Product, ReviewRating, Variation
from accounts.models import Account


def _cat(name="Tees", slug="tees"):
    return Category.objects.get_or_create(category_name=name, slug=slug)[0]


def _p(slug, name, price=20, cat=None, stock=5, compare=None, available=True):
    return Product.objects.create(product_name=name, slug=slug, price=price,
                                  category=cat or _cat(), stock=stock, is_available=available,
                                  compare_at_price=compare)


class FilterServiceTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.cheap = _p("cheap", "Cheap", price=10)
        self.mid = _p("mid", "Mid", price=50)
        self.exp = _p("exp", "Exp", price=120, compare=150)   # on sale
        Variation.objects.create(product=self.mid, variation_category="color",
                                 variation_value="Blu", is_active=True)
        Variation.objects.create(product=self.mid, variation_category="size",
                                 variation_value="M", is_active=True)

    def _ids(self, qs):
        return {p.id for p in qs}

    def test_filter_by_price_range(self):
        r = self.c.get(reverse("store"), {"min_price": 20, "max_price": 80})
        ids = self._ids(r.context["products"])
        self.assertEqual(ids, {self.mid.id})

    def test_filter_by_color_case_insensitive(self):
        r = self.c.get(reverse("store"), {"color": "blu"})   # lowercase param vs "Blu" in DB
        self.assertEqual(self._ids(r.context["products"]), {self.mid.id})

    def test_filter_by_size(self):
        r = self.c.get(reverse("store"), {"size": "m"})
        self.assertEqual(self._ids(r.context["products"]), {self.mid.id})

    def test_filter_by_sale(self):
        r = self.c.get(reverse("store"), {"sale": "1"})
        self.assertEqual(self._ids(r.context["products"]), {self.exp.id})

    def test_filter_by_rating(self):
        u = Account.objects.create_user(email="r@x.com", first_name="R", last_name="R",
                                        username="r", password="pw12345!")
        ReviewRating.objects.create(product=self.mid, user=u, rating=5, status=True)
        r = self.c.get(reverse("store"), {"rating": "4"})
        self.assertEqual(self._ids(r.context["products"]), {self.mid.id})

    def test_filter_in_stock(self):
        _p("oos", "OOS", stock=0)
        r = self.c.get(reverse("store"), {"in_stock": "1"})
        ids = self._ids(r.context["products"])
        self.assertNotIn(Product.objects.get(slug="oos").id, ids)

    def test_sort_price_asc(self):
        r = self.c.get(reverse("store"), {"sort": "price_asc"})
        prices = [p.price for p in r.context["products"]]
        self.assertEqual(prices, sorted(prices))

    def test_sort_price_desc(self):
        r = self.c.get(reverse("store"), {"sort": "price_desc"})
        prices = [p.price for p in r.context["products"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_combined_filters(self):
        r = self.c.get(reverse("store"), {"color": "blu", "size": "m", "min_price": 20})
        self.assertEqual(self._ids(r.context["products"]), {self.mid.id})

    def test_invalid_params_no_500(self):
        for params in ({"min_price": "abc"}, {"rating": "99"}, {"max_price": "-5"},
                       {"color": "<script>"}, {"sort": "garbage"}, {"min_price": "9" * 50}):
            r = self.c.get(reverse("store"), params)
            self.assertEqual(r.status_code, 200)

    def test_active_chips_present(self):
        r = self.c.get(reverse("store"), {"sale": "1", "color": "blu"})
        chips = r.context["active_chips"]
        params = {c["param"] for c in chips}
        self.assertEqual(params, {"sale", "color"})

    def test_facets_only_existing_options(self):
        r = self.c.get(reverse("store"))
        colors = {c["value"] for c in r.context["facets"]["colors"]}
        self.assertEqual(colors, {"blu"})   # only the colour that exists, lowercased

    def test_no_results_with_filters_shows_recommendations(self):
        r = self.c.get(reverse("store"), {"min_price": 99999})   # nothing matches
        self.assertEqual(r.context["product_count"], 0)
        self.assertTrue(r.context["has_filters"])
        self.assertGreaterEqual(len(r.context["recommendations"]), 1)

    def test_xss_query_param_escaped(self):
        r = self.c.get(reverse("store"), {"keyword": "<script>alert(1)</script>"})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<script>alert(1)</script>")


class FilterUrlTagTests(TestCase):
    def test_qs_remove_drops_only_one_value(self):
        from django.template import Context, Template
        from django.test import RequestFactory
        req = RequestFactory().get("/store/?color=blu&color=red&sale=1")
        t = Template("{% load shopfilters %}{% qs_remove 'color' 'blu' %}")
        out = t.render(Context({"request": req}))
        self.assertIn("color=red", out)
        self.assertIn("sale=1", out)
        self.assertNotIn("color=blu", out)

    def test_qs_set_overrides_and_drops_page(self):
        from django.template import Context, Template
        from django.test import RequestFactory
        req = RequestFactory().get("/store/?sale=1&page=3")
        t = Template("{% load shopfilters %}{% qs_set sort='newest' %}")
        out = t.render(Context({"request": req}))
        self.assertIn("sort=newest", out)
        self.assertIn("sale=1", out)
        self.assertNotIn("page=3", out)
