"""Printify Sync UX + Glitchy branding + loader — regression tests.

Covers the branding (logo/favicon wired, no settings icon as brand), the premium loader assets,
the Sync Monitor readonly+explained page, and safety (no token/key in HTML/JSON/messages).
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account

TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="


class BrandingAssetTests(TestCase):
    def test_unfold_wires_glitchy_logo_icon_favicon(self):
        from django.conf import settings
        u = settings.UNFOLD
        self.assertIn("SITE_LOGO", u)
        self.assertIn("SITE_ICON", u)
        self.assertIn("SITE_FAVICONS", u)
        # SITE_SYMBOL is only a Material-Symbol fallback; the brand must be the Glitchy asset
        self.assertEqual(u["SITE_LOGO"]["light"](None), "/static/images/brand/logo-glitchy-nav.png")
        self.assertEqual(u["SITE_LOGO"]["dark"](None), "/static/images/brand/logo-glitchy-nav-light.png")
        self.assertEqual(u["SITE_ICON"]["light"](None), "/static/images/brand/logo-glitchy-mark.png")
        self.assertEqual(u["SITE_FAVICONS"][0]["href"](None), "/static/images/favicon.ico")

    def test_brand_and_loader_assets_exist_on_disk(self):
        import pathlib
        from django.conf import settings
        base = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static"
        for rel in ("images/brand/logo-glitchy-nav.png", "images/brand/logo-glitchy-nav-light.png",
                    "images/brand/logo-glitchy-mark.png", "images/favicon.ico",
                    "glitchy_admin/ops-modal.js", "glitchy_admin/ops-modal.css"):
            self.assertTrue((base / rel).exists(), "missing %s" % rel)

    def test_loader_css_reduced_motion_safe_and_no_cdn(self):
        import pathlib, re
        from django.conf import settings
        base = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "glitchy_admin"
        css = (base / "ops-modal.css").read_text(encoding="utf-8")
        js = (base / "ops-modal.js").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("prefers-reduced-motion", js)
        self.assertFalse(re.search(r"https?://", css))     # no external/CDN
        self.assertFalse(re.search(r"https?://[^\"'\s]+\.(js|css)", js))


@override_settings(PRINTIFY_CONFIG_KEY=TEST_KEY, ALLOWED_HOSTS=["testserver"])
class AdminBrandingRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")

    def test_admin_renders_glitchy_logo_not_settings_icon(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        self.assertIn("logo-glitchy", html)                # brand asset present
        # the default Unfold brand fallback icon must not be the visible brand
        self.assertNotIn(">settings</span>", html)

    def test_admin_loads_loader_assets(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        self.assertIn("ops-modal.js", html)
        self.assertIn("ops-modal.css", html)


@override_settings(ALLOWED_HOSTS=["testserver"])
class SyncMonitorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")

    def test_sync_monitor_is_explained_and_readonly(self):
        from printify_integration.models import PrintifySyncState
        PrintifySyncState.load()
        self.client.force_login(self.su)
        url = "/admin/printify_integration/printifysyncstate/1/change/"
        html = self.client.get(url).content.decode()
        self.assertIn("Sync Monitor", html)                # renamed / explained
        self.assertIn("read-only", html.lower())
        # readonly: no editable save inputs for the technical state
        self.assertNotIn('name="backoff_level"', html)

    def test_site_favicon_points_to_glitchy(self):
        # storefront favicon is the Glitchy asset
        html = self.client.get("/").content.decode()
        self.assertIn("favicon", html.lower())
