"""Admin "Variant image mapping" operations pages + Product changelist actions.

Dry-run default, confirm-gated Apply (superadmin only), OpenAI guardrails,
run history, and no secret material in any rendered HTML.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account
from category.models import Category
from store.models import (Product, ProductColorImage, ProductColorImageMapRun,
                          ProductImage, Variation)

DASHBOARD = "/admin/store/productcolorimagemaprun/mapping/"


def _mk_product():
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    p = Product.objects.create(product_name="Adm Map Tee", slug="adm-map-tee",
                               price=20, stock=5, category=cat)
    Variation.objects.create(product=p, variation_category="color",
                             variation_value="Black", printify_variant_id="1")
    ProductImage.objects.create(product=p, printify_variant_ids="1,2",
                                printify_src="https://img.example/adm.jpg")
    return p


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"],
                   AI_API_KEY="")
class MappingAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser(
            "Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.staff = Account.objects.create_user(
            "St", "Aff", "staff@x.com", "staff", "pw-Str0ng!123")
        cls.staff.is_staff = True
        cls.staff.is_admin = True
        cls.staff.is_active = True
        cls.staff.is_superadmin = False
        cls.staff.save()

    def setUp(self):
        self.product = _mk_product()

    def test_dashboard_renders_with_openai_notice(self):
        self.client.force_login(self.su)
        resp = self.client.get(DASHBOARD)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Variant image mapping")
        self.assertContains(resp, "Run dry-run")
        self.assertContains(resp, "No OpenAI key configured")   # AI_API_KEY=""

    def test_dashboard_requires_staff(self):
        resp = self.client.get(DASHBOARD)
        self.assertEqual(resp.status_code, 302)   # redirected to admin login

    def test_preview_creates_dry_run_and_writes_nothing(self):
        self.client.force_login(self.su)
        resp = self.client.post(DASHBOARD + "preview/",
                                {"scope": "all", "source": "db"})
        run = ProductColorImageMapRun.objects.get()
        self.assertRedirects(resp, DASHBOARD + f"run/{run.pk}/")
        self.assertEqual(run.mode, "dry_run")
        self.assertEqual(ProductColorImage.objects.count(), 0)   # rolled back

    def test_result_page_shows_rows_and_apply_gate(self):
        self.client.force_login(self.su)
        self.client.post(DASHBOARD + "preview/", {"scope": "all", "source": "db"})
        run = ProductColorImageMapRun.objects.get()
        resp = self.client.get(DASHBOARD + f"run/{run.pk}/")
        self.assertContains(resp, "Mapping results")
        self.assertContains(resp, "adm map tee".title())         # product row
        self.assertContains(resp, "deterministic")
        self.assertContains(resp, "I understand this will update variant image mappings.")

    def test_result_page_hides_apply_from_staff(self):
        self.client.force_login(self.su)
        self.client.post(DASHBOARD + "preview/", {"scope": "all", "source": "db"})
        run = ProductColorImageMapRun.objects.get()
        self.client.force_login(self.staff)
        resp = self.client.get(DASHBOARD + f"run/{run.pk}/")
        self.assertNotContains(resp, "I understand this will update")
        self.assertContains(resp, "requires a superadmin")

    def test_apply_requires_superadmin(self):
        self.client.force_login(self.staff)
        resp = self.client.post(DASHBOARD + "apply/",
                                {"scope": "all", "source": "db", "confirm": "1"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(ProductColorImage.objects.count(), 0)

    def test_apply_requires_confirmation(self):
        self.client.force_login(self.su)
        resp = self.client.post(DASHBOARD + "apply/",
                                {"scope": "all", "source": "db"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ProductColorImageMapRun.objects.filter(mode="apply").exists())
        self.assertEqual(ProductColorImage.objects.count(), 0)

    def test_apply_with_confirmation_writes_maps(self):
        self.client.force_login(self.su)
        resp = self.client.post(DASHBOARD + "apply/",
                                {"scope": "all", "source": "db", "confirm": "1"},
                                follow=True)
        self.assertEqual(resp.status_code, 200)
        run = ProductColorImageMapRun.objects.get(mode="apply")
        self.assertEqual(run.colors_resolved, 1)
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_DETERMINISTIC)

    def test_single_product_scope(self):
        other = Product.objects.create(
            product_name="Other Tee", slug="other-map-tee", price=10, stock=1,
            category=self.product.category)
        Variation.objects.create(product=other, variation_category="color",
                                 variation_value="Red", printify_variant_id="9")
        self.client.force_login(self.su)
        self.client.post(DASHBOARD + "apply/",
                         {"scope": "product", "product_id": str(self.product.id),
                          "source": "db", "confirm": "1"})
        self.assertTrue(ProductColorImage.objects.filter(product=self.product).exists())
        self.assertFalse(ProductColorImage.objects.filter(product=other).exists())

    def test_changelist_dry_run_action(self):
        self.client.force_login(self.su)
        resp = self.client.post("/admin/store/product/", {
            "action": "dry_run_color_maps",
            "_selected_action": [str(self.product.id)],
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        run = ProductColorImageMapRun.objects.get()
        self.assertEqual(run.mode, "dry_run")
        self.assertEqual(ProductColorImage.objects.count(), 0)
        # the exact selection is persisted -> the result page's Apply re-runs
        # THESE ids, never a defaulted scope=all
        params = run.safe_summary_json["params"]
        self.assertEqual(params["scope"], "ids")
        self.assertEqual(params["ids"], str(self.product.id))

    def test_apply_hidden_without_stored_params(self):
        """A run with no stored params (e.g. CLI) must not offer Apply — re-running
        with defaults would silently expand the scope to the whole catalog."""
        from printify_integration.map_runner import run_color_image_mapping
        result = run_color_image_mapping(apply=False, requested_by="cli")
        self.client.force_login(self.su)
        resp = self.client.get(DASHBOARD + f"run/{result['run_id']}/")
        self.assertNotContains(resp, "I understand this will update")

    def test_run_history_not_deletable(self):
        self.client.force_login(self.su)
        self.client.post(DASHBOARD + "preview/", {"scope": "all", "source": "db"})
        run = ProductColorImageMapRun.objects.get()
        resp = self.client.post(
            f"/admin/store/productcolorimagemaprun/{run.pk}/delete/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(ProductColorImageMapRun.objects.filter(pk=run.pk).exists())

    def test_openai_action_superadmin_only(self):
        self.client.force_login(self.staff)
        self.client.post("/admin/store/product/", {
            "action": "openai_enrich_color_maps",
            "_selected_action": [str(self.product.id)],
        }, follow=True)
        self.assertFalse(ProductColorImageMapRun.objects.exists())

    def test_no_secret_material_in_pages(self):
        self.client.force_login(self.su)
        self.client.post(DASHBOARD + "preview/", {"scope": "all", "source": "db"})
        run = ProductColorImageMapRun.objects.get()
        for url in (DASHBOARD, DASHBOARD + f"run/{run.pk}/"):
            html = self.client.get(url).content.decode()
            for needle in ("sk-", "Bearer ", "token_ciphertext", "AI_API_KEY"):
                self.assertNotIn(needle, html, f"{needle} leaked into {url}")
