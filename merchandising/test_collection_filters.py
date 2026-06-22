"""Phase 36: translated mood/season labels + filtered collection landing."""
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from category.models import Category
from merchandising.models import Collection
from store.models import Product


def _product(name, price=20):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                  description="x", price=price, stock=5, category=cat,
                                  is_available=True)


def _collection(name, slug, **kw):
    c = Collection.objects.create(name=name, slug=slug, **kw)
    c.products.add(_product(name + "-p"))
    return c


class MoodSeasonLabelTests(TestCase):
    def test_labels_translated_it_fr(self):
        c = Collection.objects.create(name="X", slug="x", mood="gift_ready", season="essentials")
        with translation.override("it"):
            self.assertEqual(str(c.get_mood_display()), "Idea regalo")
            self.assertEqual(str(c.get_season_display()), "Essenziali")
        with translation.override("fr"):
            self.assertEqual(str(c.get_mood_display()), "Idée cadeau")
            self.assertEqual(str(c.get_season_display()), "Essentiels")
        with translation.override("en"):
            self.assertEqual(str(c.get_mood_display()), "Gift-ready")


class FilteredLandingTests(TestCase):
    def setUp(self):
        self.minimal = _collection("Essentials", "essentials", mood="minimal", season="essentials")
        self.bold = _collection("Drop", "drop", mood="bold", season="summer")

    def test_mood_filter_shows_only_that_mood(self):
        r = self.client.get(reverse("merchandising:collections"), {"mood": "minimal"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["active_filter"]["type"], "mood")
        self.assertEqual(r.context["active_filter"]["key"], "minimal")
        self.assertEqual(r.context["collection_count"], 1)        # only the minimal one
        self.assertEqual(r.context["featured"], [])               # featured hidden under filter

    def test_season_filter(self):
        r = self.client.get(reverse("merchandising:collections"), {"season": "summer"})
        self.assertEqual(r.context["active_filter"]["key"], "summer")
        self.assertEqual(r.context["collection_count"], 1)

    def test_filter_is_not_just_first_collection(self):
        # the filtered page lists collections of that mood, not a redirect to one
        r = self.client.get(reverse("merchandising:collections"), {"mood": "minimal"})
        self.assertEqual(r.status_code, 200)                      # 200, not 302
        self.assertIn("collx-grid", r.content.decode())

    def test_invalid_filter_falls_back(self):
        r = self.client.get(reverse("merchandising:collections"), {"mood": "zzz"})
        self.assertIsNone(r.context["active_filter"])             # ignored, full list
        self.assertEqual(r.context["collection_count"], 2)

    def test_empty_mood_not_offered(self):
        # 'street' has no collection -> not a clickable bucket
        r = self.client.get(reverse("merchandising:collections"))
        self.assertNotIn("street", [m["key"] for m in r.context["moods"]])

    def test_active_filter_noindex(self):
        html = self.client.get(reverse("merchandising:collections"), {"mood": "minimal"}).content.decode()
        self.assertIn("noindex", html)
        base = self.client.get(reverse("merchandising:collections")).content.decode()
        self.assertNotIn("noindex", base)

    def test_clear_filter_link(self):
        html = self.client.get(reverse("merchandising:collections"), {"mood": "minimal"}).content.decode()
        self.assertIn("collx-clear", html)


class AIDiscoveryMoodTests(TestCase):
    def test_context_uses_translated_labels_no_leak(self):
        from assistant.prompt import build_context
        c = Collection.objects.create(name="Gifts", slug="g", mood="gift_ready")
        p = _product("X"); p.printify_product_id = "pp_x"; p.base_cost = 9.9; p.save()
        c.products.add(p)
        with translation.override("it"):
            ctx = build_context([], [], "it", collections=[c])
        self.assertIn("Idea regalo", ctx)
        self.assertNotIn("pp_x", ctx)
        self.assertNotIn("9.9", ctx)
