import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from store.models import Category, Product
from .models import WishlistItem

User = get_user_model()


def _product(slug="p1", name="P1"):
    cat, _ = Category.objects.get_or_create(category_name="Tees", slug="tees")
    return Product.objects.create(product_name=name, slug=slug, price=20,
                                  category=cat, is_available=True, stock=5)


class WishlistTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.p = _product()

    def _toggle(self, pid):
        return self.client.post(reverse("wishlist:toggle"),
                                data=json.dumps({"product_id": pid}),
                                content_type="application/json")

    def test_guest_can_add_and_remove(self):
        r = self._toggle(self.p.id)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["in_wishlist"])
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(WishlistItem.objects.filter(user__isnull=True).count(), 1)
        # toggle again removes
        r2 = self._toggle(self.p.id)
        self.assertFalse(r2.json()["in_wishlist"])
        self.assertEqual(r2.json()["count"], 0)

    def test_authenticated_persists_to_db(self):
        u = User.objects.create_user(email="w@example.com", first_name="W", last_name="W",
                                     username="w", password="pw12345!")
        u.is_active = True; u.save()
        self.client.force_login(u)
        self._toggle(self.p.id)
        self.assertTrue(WishlistItem.objects.filter(user=u, product=self.p).exists())

    def test_toggle_requires_post(self):
        self.assertEqual(self.client.get(reverse("wishlist:toggle")).status_code, 405)

    def test_unknown_product_404(self):
        self.assertEqual(self._toggle(999999).status_code, 404)

    def test_saved_items_page_renders(self):
        self._toggle(self.p.id)
        r = self.client.get(reverse("wishlist:saved"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.p.product_name)

    def test_merge_on_login(self):
        # guest adds, then logs in -> item moves to the account
        self._toggle(self.p.id)
        sk = self.client.session.session_key
        u = User.objects.create_user(email="m@example.com", first_name="M", last_name="M",
                                     username="m", password="pw12345!")
        from .services import merge_session_to_user

        class Req:
            user = u
            session = self.client.session
        merge_session_to_user(Req(), u, session_key=sk)
        self.assertTrue(WishlistItem.objects.filter(user=u, product=self.p).exists())
        self.assertFalse(WishlistItem.objects.filter(user__isnull=True, session_key=sk,
                                                     product=self.p).exists())
