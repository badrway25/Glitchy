from unittest import mock

from django.test import TestCase

from printify_integration.services import sync_products
from store.models import Product, ProductColorImage, Variation


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


class FakeClientWithImages(FakeClient):
    """Adds per-colour mockup images (variant_ids) and a raw HTML description."""

    PRODUCT = dict(
        FakeClient.PRODUCT,
        description="<p>Soft <strong>organic</strong> tee.</p><ul><li>100% cotton</li></ul>",
        images=[
            {"src": "https://images.example/mock/a.jpg", "variant_ids": [5001],
             "position": "front", "is_default": True},
            {"src": "https://images.example/mock/b.jpg", "variant_ids": [5002],
             "position": "front"},
            {"src": "https://images.example/mock/c.jpg", "variant_ids": [5001, 5002],
             "position": "back"},
        ],
    )


@mock.patch("printify_integration.services._download_image", return_value=None)
class SyncColorImageMapTests(TestCase):
    """The sync must persist the raw description AND build the colour→image map
    deterministically from the payload (no network beyond the mocked client)."""

    def test_sync_builds_deterministic_color_map(self, _dl):
        sync_products(client=FakeClientWithImages())
        product = Product.objects.get(printify_product_id="pp_123")
        rows = {r.color_value: r for r in ProductColorImage.objects.filter(product=product)}
        self.assertEqual(set(rows), {"black", "white"})
        gallery = {img.printify_src: img.id for img in product.gallery.all()}
        black, white = rows["black"], rows["white"]
        self.assertEqual(black.source, ProductColorImage.SOURCE_DETERMINISTIC)
        # colour-specific image first, shared 'back' image appended
        self.assertEqual(black.image_id_list(),
                         [gallery["https://images.example/mock/a.jpg"],
                          gallery["https://images.example/mock/c.jpg"]])
        self.assertEqual(white.image_id_list(),
                         [gallery["https://images.example/mock/b.jpg"],
                          gallery["https://images.example/mock/c.jpg"]])
        self.assertEqual(black.primary_image_id,
                         gallery["https://images.example/mock/a.jpg"])

    def test_sync_persists_raw_and_clean_description(self, _dl):
        sync_products(client=FakeClientWithImages())
        product = Product.objects.get(printify_product_id="pp_123")
        self.assertIn("<strong>", product.printify_description_raw)   # raw kept verbatim
        self.assertNotIn("<", product.description)                    # rendered copy stays clean
        self.assertIn("• 100% cotton", product.description)

    def test_resync_keeps_map_fresh(self, _dl):
        sync_products(client=FakeClientWithImages())
        product = Product.objects.get(printify_product_id="pp_123")
        # simulate a stale/poisoned row: resync must rebuild it deterministically
        ProductColorImage.objects.filter(product=product, color_value="black").update(
            image_ids="999", source=ProductColorImage.SOURCE_HEURISTIC, confidence=0.5)
        sync_products(client=FakeClientWithImages())
        black = ProductColorImage.objects.get(product=product, color_value="black")
        self.assertEqual(black.source, ProductColorImage.SOURCE_DETERMINISTIC)
        self.assertNotEqual(black.image_ids, "999")
