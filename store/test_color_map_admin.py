"""Admin tests for the colour→image mapping surfaces.

The ProductColorImage admin must be reachable, show provenance badges, and the
Product bulk action must rebuild maps deterministically (no network)."""
from django.test import TestCase, override_settings

from accounts.models import Account
from category.models import Category
from store.models import Product, ProductColorImage, ProductImage, Variation


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ColorMapAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser(
            "Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cat = Category.objects.create(category_name="T-Shirts", slug="t-shirts")
        cls.product = Product.objects.create(
            product_name="Map Tee", slug="map-tee", price=20, stock=5, category=cat)
        Variation.objects.create(product=cls.product, variation_category="color",
                                 variation_value="Black", printify_variant_id="1",
                                 printify_title="Black / M")
        Variation.objects.create(product=cls.product, variation_category="size",
                                 variation_value="M", printify_variant_id="2",
                                 printify_title="Black / M")
        cls.img = ProductImage.objects.create(
            product=cls.product, printify_variant_ids="1,2",
            printify_src="https://images.example/a.jpg")

    def setUp(self):
        self.client.force_login(self.su)

    def test_changelist_loads_with_source_badge(self):
        ProductColorImage.objects.create(
            product=self.product, color_value="black", image_ids=str(self.img.id),
            source=ProductColorImage.SOURCE_OPENAI, confidence=0.6)
        resp = self.client.get("/admin/store/productcolorimage/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "OpenAI")
        self.assertContains(resp, "#7c3aed")   # provenance badge colour

    def test_product_action_rebuilds_maps(self):
        resp = self.client.post("/admin/store/product/", {
            "action": "rebuild_color_maps",
            "_selected_action": [str(self.product.id)],
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_DETERMINISTIC)
        self.assertEqual(row.image_id_list(), [self.img.id])

    def test_product_change_form_shows_map_inline_and_raw_description(self):
        self.product.printify_description_raw = "<p>raw &amp; original</p>"
        self.product.save()
        ProductColorImage.objects.create(
            product=self.product, color_value="black", image_ids=str(self.img.id))
        resp = self.client.get(f"/admin/store/product/{self.product.id}/change/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Colour-image map")     # inline present
        self.assertContains(resp, "Printify raw description (reference)")
