"""Phase 35: premium collection detail, mood/season, admin, AI discovery."""
from django.test import TestCase
from django.urls import reverse

from category.models import Category
from merchandising.models import Collection
from store.models import Product, Variation


def _product(name, price=20):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                  description="Nice", price=price, stock=5, category=cat,
                                  is_available=True)


def _collection(name, slug, **kw):
    c = Collection.objects.create(name=name, slug=slug, **kw)
    return c


class CollectionModelTests(TestCase):
    def test_price_range_and_colors_real(self):
        c = _collection("C1", "c1", mood="minimal", season="essentials")
        p1, p2 = _product("A", 15), _product("B", 40)
        c.products.add(p1, p2)
        Variation.objects.create(product=p1, variation_category="color", variation_value="Black")
        self.assertEqual(c.price_range(), (15.0, 40.0))
        self.assertIn("Black", c.main_colors())

    def test_related_excludes_self_and_empty(self):
        a = _collection("A", "a", mood="minimal")
        b = _collection("B", "b", mood="minimal")
        b.products.add(_product("X"))
        c_empty = _collection("E", "e", mood="minimal")  # no products
        rel = a.related(limit=3)
        self.assertIn(b, rel)
        self.assertNotIn(a, rel)         # never self
        self.assertNotIn(c_empty, rel)   # never empty

    def test_completeness_score(self):
        c = _collection("Full", "full", mood="bold", season="summer",
                        subtitle="s", editorial_intro="why", meta_description="m", image="http://x")
        c.products.add(_product("P1"), _product("P2"))
        self.assertEqual(c.completeness()["score"], 100)
        bare = _collection("Bare", "bare")
        self.assertLess(bare.completeness()["score"], 40)


class CollectionDetailTests(TestCase):
    def setUp(self):
        self.c = _collection("Essentials", "essentials", mood="minimal", season="essentials",
                             subtitle="Everyday staples", editorial_intro="The quiet core.")
        self.c.products.add(_product("Tee", 16), _product("Hoodie", 40))

    def test_detail_renders_premium_blocks(self):
        r = self.client.get(reverse("merchandising:collection", args=["essentials"]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for marker in ("cdx-hero", "cdx-editorial", "cdx-insights", "cdx-trust",
                       "CollectionPage", "BreadcrumbList"):
            self.assertIn(marker, html)
        self.assertEqual(r.context["mood_label"], "Minimal")
        self.assertEqual(r.context["product_count"], 2)
        self.assertEqual(r.context["price_min"], 16.0)

    def test_sort_price_asc(self):
        r = self.client.get(reverse("merchandising:collection", args=["essentials"]),
                            {"sort": "price_asc"})
        prices = [float(p.price) for p in r.context["products"]]
        self.assertEqual(prices, sorted(prices))

    def test_detail_no_internal_leak(self):
        p = _product("Sec", 20)
        p.printify_product_id = "pp_secret"; p.base_cost = 7.77; p.save()
        self.c.products.add(p)
        html = self.client.get(reverse("merchandising:collection", args=["essentials"])).content.decode()
        self.assertNotIn("pp_secret", html)
        self.assertNotIn("7.77", html)
        self.assertNotIn("blueprint", html.lower())

    def test_empty_state(self):
        empty = _collection("New", "new-empty")
        html = self.client.get(reverse("merchandising:collection", args=["new-empty"])).content.decode()
        self.assertIn("cdx-empty", html)


class ShopByMoodSeasonTests(TestCase):
    def test_only_real_buckets(self):
        c = _collection("M", "m", mood="bold", season="summer")
        c.products.add(_product("P"))
        _collection("EmptyMood", "em", mood="street")  # no products -> excluded
        r = self.client.get(reverse("merchandising:collections"))
        mood_keys = [m["key"] for m in r.context["moods"]]
        self.assertIn("bold", mood_keys)
        self.assertNotIn("street", mood_keys)          # empty mood not shown
        self.assertIn("summer", [s["key"] for s in r.context["seasons"]])


class AICollectionContextTests(TestCase):
    def test_context_lists_real_collections_no_leak(self):
        from assistant.prompt import build_context
        c = _collection("Drop", "drop", mood="bold")
        p = _product("X"); p.printify_product_id = "pp_x"; p.base_cost = 9.9; p.save()
        c.products.add(p)
        ctx = build_context([], [], "en", collections=[c])
        self.assertIn("COLLECTIONS:", ctx)
        self.assertIn("Drop", ctx)
        self.assertIn("mood: Bold", ctx)
        self.assertNotIn("pp_x", ctx)
        self.assertNotIn("9.9", ctx)
