"""Admin Forms Premium Polish — regression tests.

Covers the root-cause fix (custom-form widgets get Unfold's classes so inputs are visible),
the slim add form (auto/readonly fields hidden on create), the category unused-field removal,
the order add being disabled, and — critically — that the token never leaks.
"""
from django.test import TestCase, override_settings

from accounts.models import Account
from printify_integration.models import PrintifyAccountConfig

TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
SECRET = "printify-forms-token-DoNotLeak"


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PrintifyConfigFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")

    def _base(self):
        return "/admin/printify_integration/printifyaccountconfig/"

    def test_add_form_inputs_are_styled_not_bare(self):
        # the fix: custom-form widgets receive Unfold's input classes (border/padding), so they
        # are visible instead of the bare 20px vTextField.
        self.client.force_login(self.su)
        html = self.client.get(self._base() + "add/").content.decode()
        import re
        m = re.search(r'<input[^>]*name="name"[^>]*>', html)
        self.assertIsNotNone(m)
        self.assertIn("border", m.group(0))          # Unfold input class applied

    def test_add_form_hides_auto_and_readonly_fields(self):
        self.client.force_login(self.su)
        html = self.client.get(self._base() + "add/").content.decode()
        for gone in ("Connection status", "Token status", "Created at", "Updated at", "Token set at"):
            self.assertNotIn(gone, html)

    def test_change_form_shows_status_and_meta(self):
        cfg = PrintifyAccountConfig(name="Primary", is_active=True, shop_id="1")
        cfg.set_token(SECRET, by="adm")
        cfg.save()
        self.client.force_login(self.su)
        html = self.client.get(self._base() + f"{cfg.id}/change/").content.decode()
        self.assertIn("Connection status", html)
        self.assertIn("Created at", html)
        self.assertNotIn(SECRET, html)               # token still never leaks
        self.assertNotIn(TEST_KEY, html)

    def test_add_form_never_leaks_token_or_key(self):
        cfg = PrintifyAccountConfig(name="P", is_active=True)
        cfg.set_token(SECRET, by="adm")
        cfg.save()
        self.client.force_login(self.su)
        html = self.client.get(self._base() + "add/").content.decode()
        self.assertNotIn(SECRET, html)
        self.assertNotIn(TEST_KEY, html)


class OrderAndCategoryAdminTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_order_add_is_disabled_not_500(self):
        su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        self.client.force_login(su)
        resp = self.client.get("/admin/orders/order/add/")
        self.assertEqual(resp.status_code, 403)      # add disabled (was a 500 FieldError)

    def test_category_admin_hides_unused_image_field(self):
        from category.admin import CategoryAdmin
        from django.contrib.admin.sites import site
        from category.models import Category
        a = CategoryAdmin(Category, site)
        # cat_image must not be in any fieldset
        fields = [f for _name, opts in a.fieldsets for f in opts["fields"]]
        self.assertNotIn("cat_image", fields)

    def test_forms_css_wired_and_no_cdn(self):
        import pathlib
        from django.conf import settings
        css = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "glitchy_admin" / "forms.css"
        self.assertTrue(css.exists())
        text = css.read_text(encoding="utf-8")
        import re
        self.assertFalse(re.search(r"https?://", text))   # no external/CDN
        self.assertIn("prefers-reduced-motion", text)
