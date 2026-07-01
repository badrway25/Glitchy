"""Printify admin: connection + shop discovery + catalog import — flow tests.

The Printify API is MOCKED (no real network, the owner's real token is never used). Covers the
owner's requirement: no manual shop_id, Discover shops -> Use this shop -> Sync, all from the
admin, token never leaked, no publish/order, local catalogue only.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account
from category.models import Category
from printify_integration.models import PrintifyAccountConfig
from store.models import Product

TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
SECRET = "printify-flow-token-SECRET"

SHOPS = [
    {"id": 12345, "title": "Fabricon", "sales_channel": "custom_integration"},
    {"id": 67890, "title": "Other shop", "sales_channel": "shopify"},
]


def _product(pid, title, price_cents=2000, with_image=True, visible=True):
    p = {"id": pid, "title": title, "description": "<p>desc</p>", "visible": visible,
         "blueprint_id": 145, "print_provider_id": 1, "tags": ["tee"], "options": [],
         "variants": [{"id": 1, "price": price_cents, "cost": 800, "is_enabled": True,
                       "is_available": True, "title": "M", "options": []}]}
    if with_image:
        p["images"] = [{"src": "https://img/x.png", "is_default": True}]
    return p


def _mock_client(products_pages):
    c = MagicMock()
    c.get_shops.return_value = SHOPS
    def _list(shop_id=None, limit=50, page=1):
        return {"data": products_pages[page - 1] if page - 1 < len(products_pages) else []}
    c.list_products.side_effect = _list
    return c


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"],
                   PRINTIFY_PUSH_ENABLED=False)
class PrintifyAdminFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.staff = Account.objects.create_user("St", "Aff", "staff@x.com", "staff", "pw-Str0ng!123")
        cls.staff.is_staff = True
        cls.staff.is_admin = True
        cls.staff.is_active = True
        cls.staff.is_superadmin = False
        cls.staff.save()
        Category.objects.get_or_create(slug="t-shirt", defaults={"category_name": "T-Shirts"})

    def _cfg(self, token=SECRET, shop_id=""):
        cfg = PrintifyAccountConfig(name="pollo", is_active=True, shop_id=shop_id)
        if token:
            cfg.set_token(token, by="adm")
        cfg.save()
        return cfg

    def _u(self, name, *args):
        return reverse("admin:printify_integration_printifyaccountconfig_" + name, args=args)

    # -- buttons + shop_id not a manual field --------------------------------
    def test_change_form_shows_ops_buttons_when_token_present(self):
        cfg = self._cfg()
        self.client.force_login(self.su)
        html = self.client.get(self._u("change", cfg.id)).content.decode()
        self.assertIn("Printify operations", html)
        self.assertIn("Discover shops", html)
        self.assertIn("Test connection", html)
        self.assertNotIn('name="shop_id"', html)          # shop_id is NOT a manual field

    def test_add_form_has_no_shop_id_field(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/printify_integration/printifyaccountconfig/add/").content.decode()
        self.assertNotIn('name="shop_id"', html)

    def test_buttons_hidden_without_token(self):
        cfg = self._cfg(token="")
        self.client.force_login(self.su)
        html = self.client.get(self._u("change", cfg.id)).content.decode()
        self.assertIn("Save an API token first", html)

    # -- discover shops ------------------------------------------------------
    def test_discover_shops_lists_shops(self):
        cfg = self._cfg(shop_id="Fabricon")
        self.client.force_login(self.su)
        with patch("printify_integration.services.client_for_config", return_value=_mock_client([])):
            self.client.post(self._u("discover", cfg.id))
        html = self.client.get(self._u("change", cfg.id)).content.decode()
        self.assertIn("12345", html)                       # numeric id shown
        self.assertIn("Other shop", html)
        self.assertIn("suggested", html)                   # Fabricon title matches legacy shop_id

    def test_use_shop_saves_numeric_id(self):
        cfg = self._cfg(shop_id="Fabricon")
        self.client.force_login(self.su)
        with patch("printify_integration.services.client_for_config", return_value=_mock_client([])):
            self.client.post(self._u("discover", cfg.id))
            self.client.post(self._u("use_shop", cfg.id, "12345"))
        cfg.refresh_from_db()
        self.assertEqual(cfg.shop_id, "12345")
        self.assertEqual(cfg.shop_title, "Fabricon")
        self.assertTrue(cfg.has_valid_shop())

    def test_fabricon_shop_id_is_invalid_and_warned(self):
        cfg = self._cfg(shop_id="Fabricon")
        self.client.force_login(self.su)
        html = self.client.get(self._u("change", cfg.id)).content.decode()
        self.assertFalse(cfg.has_valid_shop())
        self.assertIn("not a numeric Printify shop ID", html)

    # -- catalog import ------------------------------------------------------
    def test_sync_creates_and_hides_products(self):
        cfg = self._cfg(shop_id="12345")
        self.client.force_login(self.su)
        pages = [[_product("p1", "Good Tee"), _product("p2", "No Image Tee", with_image=False)]]
        with patch("printify_integration.services.client_for_config", return_value=_mock_client(pages)):
            self.client.post(self._u("sync", cfg.id))
        self.assertTrue(Product.objects.filter(printify_product_id="p1").exists())
        no_img = Product.objects.get(printify_product_id="p2")
        self.assertFalse(no_img.is_available)              # missing image -> hidden / to review

    def test_dry_run_writes_nothing(self):
        cfg = self._cfg(shop_id="12345")
        self.client.force_login(self.su)
        pages = [[_product("d1", "Dry Tee")]]
        with patch("printify_integration.services.client_for_config", return_value=_mock_client(pages)):
            self.client.post(self._u("dryrun", cfg.id))
        self.assertFalse(Product.objects.filter(printify_product_id="d1").exists())

    def test_sync_refuses_non_numeric_shop(self):
        cfg = self._cfg(shop_id="Fabricon")
        self.client.force_login(self.su)
        from printify_integration.services import import_catalog_from_config
        report, _log = import_catalog_from_config(cfg, apply=True)
        self.assertIn("numeric", report["error"])
        self.assertEqual(report["created"], 0)

    # -- security ------------------------------------------------------------
    def test_token_never_leaks_in_ops_flow(self):
        cfg = self._cfg(shop_id="12345")
        self.client.force_login(self.su)
        html = self.client.get(self._u("change", cfg.id)).content.decode()
        self.assertNotIn(SECRET, html)
        self.assertNotIn(TEST_KEY, html)

    def test_non_superadmin_cannot_discover_or_sync(self):
        cfg = self._cfg(shop_id="12345")
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self._u("discover", cfg.id)).status_code, 403)
        self.assertEqual(self.client.post(self._u("sync", cfg.id)).status_code, 403)

    def test_sync_calls_no_publish_or_order_endpoint(self):
        cfg = self._cfg(shop_id="12345")
        self.client.force_login(self.su)
        mock = _mock_client([[_product("p9", "Tee")]])
        with patch("printify_integration.services.client_for_config", return_value=mock):
            self.client.post(self._u("sync", cfg.id))
        # only read endpoints were used
        called = [c[0] for c in mock.method_calls]
        for forbidden in ("publish", "create_order", "submit"):
            self.assertFalse(any(forbidden in m for m in called), "called %s" % called)
