"""Phase 33: Printify description sanitization + customer/AI safety."""
from django.test import TestCase

from category.models import Category
from store.models import Product, Variation
from printify_integration.text import clean_printify_description, looks_like_html


class SanitizerTests(TestCase):
    def test_strips_block_tags_to_text(self):
        out = clean_printify_description("<p>Hello <b>world</b></p><br>Line2")
        self.assertNotIn("<", out)
        self.assertIn("Hello world", out)
        self.assertIn("Line2", out)

    def test_lists_become_bullets(self):
        out = clean_printify_description("<ul><li>One</li><li>Two</li></ul>")
        self.assertIn("• One", out)
        self.assertIn("• Two", out)
        self.assertNotIn("<li>", out)

    def test_removes_script_and_xss(self):
        out = clean_printify_description('<script>alert("x")</script>Safe<img src=x onerror=alert(1)>')
        self.assertNotIn("script", out.lower())
        self.assertNotIn("alert", out.lower())
        self.assertNotIn("onerror", out.lower())
        self.assertIn("Safe", out)

    def test_malformed_html_is_safe(self):
        out = clean_printify_description("<p>unclosed <b>bold <i>x")
        self.assertNotIn("<", out)
        self.assertIn("unclosed", out)

    def test_entities_unescaped(self):
        self.assertEqual(clean_printify_description("Tom &amp; Jerry &lt;3"), "Tom & Jerry <3")

    def test_looks_like_html(self):
        self.assertTrue(looks_like_html("<p>x</p>"))
        self.assertFalse(looks_like_html("plain text"))

    def test_empty(self):
        self.assertEqual(clean_printify_description(None), "")


class SyncAndDisplayTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(category_name="C", slug="c")

    def _product(self, desc):
        return Product.objects.create(product_name="Tee", slug="tee", description=desc,
                                      price=20, stock=5, category=self.cat,
                                      printify_blueprint_id=145)

    def test_sync_sanitizes_description(self):
        from printify_integration.services import _upsert_product
        payload = {"id": "pp_x", "title": "Tee", "blueprint_id": 145, "print_provider_id": 99,
                   "description": "<p>Soft tee</p><ul><li>Cotton</li></ul>",
                   "visible": True, "variants": [], "images": [], "options": []}
        obj, _ = _upsert_product(payload, self.cat, {}, False)
        self.assertNotIn("<", obj.description)
        self.assertIn("Soft tee", obj.description)
        self.assertIn("• Cotton", obj.description)

    def test_pdp_shows_no_raw_tags(self):
        p = self._product("Soft tee. Comfortable.")   # already-clean stored text
        html = self.client.get(p.get_url()).content.decode()
        # the sanitized text renders; no literal escaped tags shown to the customer
        self.assertNotIn("&lt;p&gt;", html)
        self.assertNotIn("&lt;br&gt;", html)

    def test_meta_description_is_single_line(self):
        p = self._product("Line one\nLine two\nLine three " + "x" * 300)
        md = p.meta_description()
        self.assertNotIn("\n", md)
        self.assertTrue(md.endswith("…"))
        self.assertLessEqual(len(md), 161)

    def test_ai_context_has_clean_description(self):
        from assistant.prompt import build_context
        p = self._product("Cotton tee, very soft")
        ctx = build_context([], [p], "en")
        self.assertIn("Cotton tee", ctx)
        self.assertNotIn("<", ctx)
