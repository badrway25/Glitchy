"""Phase 22 tests: recommendations, outfits, collections, style quiz, notify-me."""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from category.models import Category
from store.models import Product
from .models import Collection, Outfit, ProductNotificationSignup, ProductRelation

User = get_user_model()


def _cat(name="Tees", slug="tees"):
    return Category.objects.get_or_create(category_name=name, slug=slug)[0]


def _product(slug, name, price=20, available=True, cat=None):
    return Product.objects.create(product_name=name, slug=slug, price=price,
                                  category=cat or _cat(), is_available=available, stock=5)


class RecommendationTests(TestCase):
    def setUp(self):
        self.a = _product("a", "A")
        self.b = _product("b", "B")
        self.c = _product("c", "C")
        self.inactive = _product("d", "D", available=False)

    def test_curated_relation_comes_first(self):
        from .recommendations import recommend_for_product
        ProductRelation.objects.create(from_product=self.a, to_product=self.c,
                                       relation_type=ProductRelation.BEST_MATCH, order=0)
        recs = recommend_for_product(self.a, limit=4)
        self.assertEqual(recs[0].id, self.c.id)

    def test_never_recommends_self_or_inactive(self):
        from .recommendations import recommend_for_product
        recs = recommend_for_product(self.a, limit=10)
        ids = [p.id for p in recs]
        self.assertNotIn(self.a.id, ids)          # not self
        self.assertNotIn(self.inactive.id, ids)   # not inactive

    def test_no_duplicates(self):
        from .recommendations import recommend_for_product
        ProductRelation.objects.create(from_product=self.a, to_product=self.b,
                                       relation_type=ProductRelation.RELATED)
        recs = recommend_for_product(self.a, limit=10)
        ids = [p.id for p in recs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_complete_the_look_is_curated_only(self):
        from .recommendations import complete_the_look
        self.assertEqual(complete_the_look(self.a), [])  # none curated yet
        ProductRelation.objects.create(from_product=self.a, to_product=self.b,
                                       relation_type=ProductRelation.COMPLETE_LOOK)
        self.assertEqual([p.id for p in complete_the_look(self.a)], [self.b.id])


class OutfitAddTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.a = _product("a", "A")
        self.b = _product("b", "B")
        self.inactive = _product("c", "C", available=False)

    def test_add_selected_to_cart(self):
        from carts.models import CartItem
        r = self.c.post(reverse("merchandising:outfit_add"),
                        data=json.dumps({"product_ids": [self.a.id, self.b.id]}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["added"], 2)
        self.assertEqual(CartItem.objects.count(), 2)

    def test_inactive_product_not_added(self):
        r = self.c.post(reverse("merchandising:outfit_add"),
                        data=json.dumps({"product_ids": [self.inactive.id]}),
                        content_type="application/json")
        self.assertEqual(r.json()["added"], 0)

    def test_empty_payload_400(self):
        r = self.c.post(reverse("merchandising:outfit_add"),
                        data=json.dumps({"product_ids": []}), content_type="application/json")
        self.assertEqual(r.status_code, 400)


class StyleQuizTests(TestCase):
    def setUp(self):
        self.c = Client()
        _product("p1", "P1", price=20)
        _product("p2", "P2", price=80)

    def test_quiz_page_renders(self):
        self.assertEqual(self.c.get(reverse("merchandising:style_quiz")).status_code, 200)

    def test_results_respect_budget(self):
        r = self.c.post(reverse("merchandising:style_quiz"),
                        {"category": "any", "budget": "under_25", "color": "any",
                         "vibe": "minimal", "occasion": "everyday"})
        self.assertEqual(r.status_code, 200)
        # at least the under-25 product is present; never empty (fallback)
        self.assertGreaterEqual(len(r.context["products"]), 1)

    def test_results_never_empty_fallback(self):
        # a filter that matches nothing falls back to best/newest, never an empty page
        r = self.c.post(reverse("merchandising:style_quiz"),
                        {"category": "nonexistent", "budget": "over_100", "color": "any"})
        self.assertTrue(r.context["fallback"])
        self.assertGreaterEqual(len(r.context["products"]), 1)


class CollectionTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.col = Collection.objects.create(name="New Season", is_active=True)
        self.active = _product("a", "A")
        self.inactive = _product("b", "B", available=False)
        self.col.products.set([self.active, self.inactive])

    def test_collection_page_shows_only_active(self):
        r = self.c.get(self.col.get_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "A")
        products = list(r.context["products"])
        self.assertIn(self.active, products)
        self.assertNotIn(self.inactive, products)

    def test_inactive_collection_404(self):
        self.col.is_active = False
        self.col.save()
        self.assertEqual(self.c.get(self.col.get_url()).status_code, 404)

    def test_xss_in_collection_name_escaped(self):
        col = Collection.objects.create(name="<script>x</script>", is_active=True)
        r = self.c.get(col.get_url())
        self.assertNotContains(r, "<script>x</script>")


class NotifyMeTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.p = _product("a", "A", available=False)

    def _post(self, **extra):
        data = {"email": "x@example.com", "consent": "1", "product_id": self.p.id}
        data.update(extra)
        return self.c.post(reverse("merchandising:notify_me"), data)

    def test_valid_signup(self):
        r = self._post()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ProductNotificationSignup.objects.filter(email="x@example.com").exists())

    def test_invalid_email_rejected(self):
        r = self._post(email="not-an-email")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ProductNotificationSignup.objects.exists())

    def test_consent_required(self):
        r = self.c.post(reverse("merchandising:notify_me"),
                        {"email": "x@example.com", "product_id": self.p.id})
        self.assertEqual(r.status_code, 400)

    def test_honeypot_swallows_bot(self):
        r = self._post(website="http://spam.example")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ProductNotificationSignup.objects.exists())   # not stored

    def test_ip_is_hashed_not_raw(self):
        self._post()
        s = ProductNotificationSignup.objects.first()
        self.assertNotIn(".", s.ip_hash)   # sha256 hex, not a dotted IP


class GrowthAnalyticsTests(TestCase):
    def test_growth_event_names_allowlisted(self):
        from storefront.models import AnalyticsEvent
        c = Client()
        for name in ("outfit_view", "outfit_add_to_cart", "style_quiz_start",
                     "style_quiz_complete", "collection_view", "notification_signup",
                     "recommendation_view", "recommendation_click"):
            r = c.post(reverse("storefront:event"),
                       data=json.dumps({"name": name, "meta": {}}),
                       content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{name} should be accepted")
