from django.test import TestCase

from printify_integration.services import sync_products
from store.models import Product, Variation


class FakeClient:
    """Mimics PrintifyClient.list_products without any network calls."""

    PRODUCT = {
        "id": "pp_123",
        "title": "Organic Tee",
        "description": "Soft organic cotton tee.",
        "visible": True,
        "blueprint_id": 145,
        "print_provider_id": 99,
        "images": [],  # no images -> no downloads
        "options": [
            {"type": "color", "values": [{"id": 1, "title": "Black"}, {"id": 2, "title": "White"}]},
            {"type": "size", "values": [{"id": 10, "title": "M"}, {"id": 11, "title": "L"}]},
        ],
        "variants": [
            {"id": 5001, "is_enabled": True, "price": 2990, "cost": 1200, "options": [1, 10]},
            {"id": 5002, "is_enabled": True, "price": 2990, "cost": 1250, "options": [2, 11]},
        ],
    }

    def list_products(self, limit=50, page=1):
        return {"data": [self.PRODUCT]} if page == 1 else {"data": []}

    def get_product(self, product_id):
        return self.PRODUCT


class PrintifySyncTests(TestCase):
    def test_sync_creates_product_with_cost(self):
        log = sync_products(client=FakeClient())
        self.assertEqual(log.status, "ok")
        self.assertEqual(log.created_count, 1)

        product = Product.objects.get(printify_product_id="pp_123")
        self.assertEqual(product.product_name, "Organic Tee")
        self.assertEqual(product.price, 30)              # 2990 cents -> ~30 EUR
        self.assertEqual(product.base_cost, 12.0)        # min variant cost 1200 -> 12.00
        self.assertEqual(product.printify_blueprint_id, 145)
        self.assertEqual(product.printify_provider_id, 99)
        self.assertEqual(product.printify_sync_status, Product.SYNC_SYNCED)

    def test_variations_synced_with_cost(self):
        sync_products(client=FakeClient())
        product = Product.objects.get(printify_product_id="pp_123")
        colors = Variation.objects.filter(product=product, variation_category="color")
        sizes = Variation.objects.filter(product=product, variation_category="size")
        self.assertEqual(colors.count(), 2)
        self.assertEqual(sizes.count(), 2)
        black = colors.get(variation_value__iexact="Black")
        self.assertEqual(black.printify_variant_id, "5001")
        self.assertGreater(black.production_cost, 0)

    def test_resync_is_idempotent(self):
        sync_products(client=FakeClient())
        log2 = sync_products(client=FakeClient())
        self.assertEqual(log2.updated_count, 1)
        self.assertEqual(Product.objects.filter(printify_product_id="pp_123").count(), 1)
