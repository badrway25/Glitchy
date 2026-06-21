import json

from django.test import Client, TestCase
from django.urls import reverse

from .models import AnalyticsEvent, Announcement


class AnalyticsEventTests(TestCase):
    def test_valid_event_is_recorded(self):
        r = self.client.post(reverse("storefront:event"),
                             data=json.dumps({"name": "product_view", "meta": {"id": "5"}}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(AnalyticsEvent.objects.filter(name="product_view").exists())

    def test_unknown_event_rejected(self):
        r = self.client.post(reverse("storefront:event"),
                             data=json.dumps({"name": "totally_made_up"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(AnalyticsEvent.objects.exists())

    def test_event_requires_post(self):
        self.assertEqual(self.client.get(reverse("storefront:event")).status_code, 405)


class AnnouncementTests(TestCase):
    def test_localized_message(self):
        a = Announcement.objects.create(message="Hello", message_it="Ciao", message_fr="Salut")
        self.assertEqual(a.message_for("it"), "Ciao")
        self.assertEqual(a.message_for("fr"), "Salut")
        self.assertEqual(a.message_for("en"), "Hello")
        self.assertEqual(a.message_for("de"), "Hello")  # fallback

    def test_context_processor_exposes_active(self):
        Announcement.objects.create(message="Sale!", is_active=True)
        from storefront.context_processors import announcement
        req = Client().get("/").wsgi_request
        ctx = announcement(req)
        self.assertIsNotNone(ctx["ANNOUNCEMENT"])
        self.assertEqual(ctx["ANNOUNCEMENT"]["message"], "Sale!")


class RecentlyViewedTests(TestCase):
    def test_record_and_retrieve(self):
        from store.models import Category, Product
        cat = Category.objects.create(category_name="Tees", slug="tees")
        p1 = Product.objects.create(product_name="A", slug="a", price=10, category=cat, is_available=True, stock=5)
        p2 = Product.objects.create(product_name="B", slug="b", price=20, category=cat, is_available=True, stock=5)
        from storefront.recently import record_view, get_recently_viewed
        req = self.client.get("/").wsgi_request
        record_view(req, p1.id)
        record_view(req, p2.id)
        rv = get_recently_viewed(req, exclude_id=p2.id)
        self.assertEqual([p.id for p in rv], [p1.id])
