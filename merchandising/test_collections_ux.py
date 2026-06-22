"""Phase 34: premium navbar search + collections landing UX."""
from django.test import TestCase
from django.urls import reverse

from category.models import Category
from merchandising.models import Collection
from store.models import Product


def _product(name):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                  description="x", price=20, stock=5, category=cat,
                                  is_available=True)


class NavbarSearchTests(TestCase):
    def test_no_duplicate_search_icon_or_overlay(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("mobile-search-trigger", html)   # duplicate icon removed
        self.assertNotIn('id="mobileSearch"', html)        # redundant overlay removed

    def test_premium_search_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("searchbar-xl", html)                # upgraded search bar
        self.assertIn("nav-search", html)
        self.assertIn('name="keyword"', html)              # still a working search field

    def test_nav_has_core_links(self):
        html = self.client.get(reverse("home")).content.decode()
        for url in (reverse("store"), reverse("merchandising:collections")):
            self.assertIn(url, html)


class CollectionsIndexTests(TestCase):
    def test_index_200(self):
        r = self.client.get(reverse("merchandising:collections"))
        self.assertEqual(r.status_code, 200)

    def test_index_shows_real_counts_and_sections(self):
        c = Collection.objects.create(name="New Season", slug="new-season", featured=True,
                                      subtitle="Fresh arrivals")
        c.products.add(_product("Tee A"), _product("Tee B"))
        r = self.client.get(reverse("merchandising:collections"))
        self.assertEqual(r.context["collection_count"], 1)
        self.assertEqual(r.context["total_products"], 2)
        html = r.content.decode()
        self.assertIn("collx-hero", html)
        self.assertIn("collx-featured", html)
        self.assertIn("collx-editorial", html)
        self.assertIn("CollectionPage", html)              # JSON-LD
        self.assertIn("BreadcrumbList", html)

    def test_featured_requires_products(self):
        Collection.objects.create(name="Empty", slug="empty", featured=True)  # 0 products
        r = self.client.get(reverse("merchandising:collections"))
        self.assertEqual(len(r.context["featured"]), 0)    # no featured card without pieces

    def test_empty_state(self):
        r = self.client.get(reverse("merchandising:collections"))
        html = r.content.decode()
        self.assertIn("collx-empty", html)
        self.assertIn(reverse("store"), html)

    def test_no_internal_ids_or_costs_leaked(self):
        c = Collection.objects.create(name="C1", slug="c1")
        p = _product("Secret")
        p.printify_product_id = "pp_secret_x"; p.base_cost = 7.77; p.save()
        c.products.add(p)
        html = self.client.get(reverse("merchandising:collections")).content.decode()
        self.assertNotIn("pp_secret_x", html)
        self.assertNotIn("7.77", html)

    def test_detail_still_works(self):
        c = Collection.objects.create(name="D", slug="d")
        c.products.add(_product("X"))
        r = self.client.get(reverse("merchandising:collection", args=["d"]))
        self.assertEqual(r.status_code, 200)
