"""Phase 31: deep Printify variant/image enrichment, dashboard, safety."""
from django.test import TestCase
from django.contrib.auth import get_user_model

from category.models import Category
from store.models import Product, ProductImage, Variation


def _product(name="Tee", **kw):
    cat = Category.objects.get_or_create(category_name="Cat", slug="cat")[0]
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description="Nice",
             price=20, stock=10, category=cat, is_available=True,
             printify_blueprint_id=145, printify_provider_id=99,
             printify_blueprint_title="Tee BP", printify_provider_name="Provider X")
    d.update(kw)
    return Product.objects.create(**d)


FAKE_PAYLOAD = {
    "id": "pp_1", "title": "Tee", "blueprint_id": 145, "print_provider_id": 99,
    "visible": True, "tags": ["summer"],
    "options": [{"name": "Colors", "type": "color", "values": [{"id": 1, "title": "Black"}]},
                {"name": "Sizes", "type": "size", "values": [{"id": 10, "title": "M"}]}],
    "variants": [
        {"id": 111, "sku": "SKU-111", "title": "Black / M", "price": 2000, "cost": 900,
         "grams": 180, "is_enabled": True, "is_available": True, "is_default": True,
         "options": [1, 10]},
        {"id": 112, "sku": "SKU-112", "title": "Black / L", "price": 2000, "cost": 900,
         "grams": 200, "is_enabled": False, "options": [1]},  # disabled -> skipped
    ],
    "images": [
        {"src": "https://img/x.png", "is_default": True, "position": "front",
         "mockup_id": "mk1", "variant_ids": [111, 112], "order": 0},
    ],
}


class VariantEnrichmentTests(TestCase):
    def test_variant_fields_mapped(self):
        from printify_integration.services import _sync_variations
        p = _product("V")
        _sync_variations(p, FAKE_PAYLOAD)
        black = Variation.objects.filter(product=p, variation_value__iexact="Black").first()
        self.assertIsNotNone(black)
        self.assertEqual(black.printify_sku, "SKU-111")
        self.assertEqual(black.printify_grams, 180)
        self.assertEqual(black.production_cost, 9.0)          # 900 cents
        self.assertTrue(black.printify_is_enabled)
        self.assertTrue(black.is_buyable)
        self.assertEqual(black.margin(), 11.0)                # 20 - 9

    def test_sync_is_idempotent(self):
        from printify_integration.services import _sync_variations
        p = _product("Idem")
        _sync_variations(p, FAKE_PAYLOAD)
        n1 = Variation.objects.filter(product=p).count()
        _sync_variations(p, FAKE_PAYLOAD)
        self.assertEqual(Variation.objects.filter(product=p).count(), n1)   # no duplicates

    def test_disabled_variant_not_buyable(self):
        v = Variation.objects.create(product=_product("D"), variation_category="size",
                                     variation_value="XL", printify_is_enabled=False)
        self.assertFalse(v.is_buyable)


class ImageEnrichmentTests(TestCase):
    def test_image_metadata_without_download(self):
        from printify_integration.services import _sync_images
        p = _product("Img")
        # network download will fail in tests -> rows still created with metadata
        _sync_images(p, FAKE_PAYLOAD, refresh=True)
        img = ProductImage.objects.filter(product=p).first()
        self.assertIsNotNone(img)
        self.assertEqual(img.printify_position, "front")
        self.assertTrue(img.is_default)
        self.assertIn("111", img.printify_variant_ids)
        self.assertTrue(img.display_url())   # falls back to printify_src


class DashboardTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.staff = U.objects.create_user(email="s@x.com", username="s", password="pw12345!",
                                           first_name="S", last_name="T")
        self.staff.is_staff = True; self.staff.is_admin = True; self.staff.is_active = True
        self.staff.save()

    def test_dashboard_renders_no_pii_no_secret(self):
        _product("Dash", printify_product_id="pp_secret_999")
        self.client.force_login(self.staff)
        r = self.client.get("/admin/printify-dashboard/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Printify operations dashboard", html)
        self.assertIn("Avg data quality", html)
        # full secret product id must be masked (only short form), never the raw token
        self.assertNotIn("pp_secret_999", html)

    def test_dashboard_requires_staff(self):
        r = self.client.get("/admin/printify-dashboard/")
        self.assertIn(r.status_code, (301, 302))   # redirected to admin login
