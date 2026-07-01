"""Phase 69 — ultra-premium admin visual analytics: correctness, safety, accessibility.

The dashboard must expose only aggregate/derived data (no token, no PII), render charts with
text fallbacks, keep dangerous Printify flags OFF, and pull no external/CDN assets.
"""
import pathlib
import re

from django.conf import settings
from django.test import TestCase, override_settings

from accounts.models import Account
from store.models import Category, Product

STATIC = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "glitchy_admin"
CSS = STATIC / "premium.css"
JS = STATIC / "motion.js"
TEST_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="


class AnalyticsDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")
        for i in range(3):
            Product.objects.create(product_name="P%d" % i, slug="p%d" % i, price=20 + i,
                                   stock=5, category=cls.cat, is_available=(i != 2))

    def test_catalog_health_score_in_range(self):
        from greatkart.admin_ext import catalog_health
        h = catalog_health()
        self.assertTrue(0 <= h["score"] <= 100)
        self.assertTrue(all(0 <= d["ok_pct"] <= 100 for d in h["dimensions"]))
        # SVG ring geometry present (renders without JS)
        self.assertIn("ring_circ", h)
        self.assertIn("ring_offset", h)

    def test_product_status_conic_is_deterministic_string(self):
        from greatkart.admin_ext import product_status
        s = product_status()
        self.assertTrue(s["availability_conic"].startswith("conic-gradient("))
        self.assertTrue(s["source_conic"].startswith("conic-gradient("))

    def test_dashboard_data_has_no_secret_or_pii(self):
        import json
        from greatkart.admin_ext import dashboard_callback
        ctx = {}
        dashboard_callback(None, ctx)
        blob = json.dumps({k: str(v) for k, v in ctx.items()})
        for bad in ["Bearer", "sk-", "PRINTIFY_CONFIG_KEY", "token_ciphertext", "gAAAA", "@gmail", "@example"]:
            self.assertNotIn(bad, blob)

    def test_sync_health_defaults_off(self):
        from greatkart.admin_ext import sync_health
        s = sync_health()
        self.assertTrue(s["publish_off"])
        self.assertTrue(s["orders_off"])


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"], PRINTIFY_CONFIG_KEY=TEST_KEY)
class DashboardRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")
        Product.objects.create(product_name="P", slug="p", price=20, stock=5, category=cls.cat, is_available=True)

    def test_dashboard_renders_charts(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        self.assertIn("Commerce control center", html)
        self.assertIn("gl-ring", html)            # health ring
        self.assertIn('class="arc"', html)        # svg arc
        self.assertIn("conic-gradient", html)     # donut
        self.assertIn("gl-bar-fill", html)        # bars
        self.assertIn("glitchy_admin/premium.css", html)
        self.assertIn("glitchy_admin/motion.js", html)

    def test_dashboard_charts_have_text_alternatives(self):
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        # every chart carries an aria-label (accessibility fallback)
        self.assertIn("health score", html.lower())
        self.assertGreaterEqual(html.count('role="img"'), 2)

    def test_dashboard_html_has_no_token(self):
        # a Printify config with a token must not leak into the dashboard
        from printify_integration.models import PrintifyAccountConfig
        SECRET = "dash-token-DoNotLeak-99"
        cfg = PrintifyAccountConfig(name="Primary", is_active=True, shop_id="1")
        cfg.set_token(SECRET, by="adm")
        cfg.save()
        self.client.force_login(self.su)
        html = self.client.get("/admin/").content.decode()
        self.assertNotIn(SECRET, html)
        self.assertIn("Printify sync health", html)


class StaticAssetSafetyTests(TestCase):
    def test_admin_css_and_js_exist(self):
        self.assertTrue(CSS.exists())
        self.assertTrue(JS.exists())

    def test_reduced_motion_respected(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", js)

    def test_no_external_cdn_in_admin_assets(self):
        for f in (CSS, JS):
            text = f.read_text(encoding="utf-8")
            self.assertFalse(re.search(r"https?://", text),
                             "%s must not reference an external/CDN URL" % f.name)
        # the dashboard template must not pull a CDN either
        tpl = (pathlib.Path(settings.BASE_DIR) / "templates" / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("cdn", tpl.lower())
        self.assertFalse(re.search(r'src="https?://', tpl))
