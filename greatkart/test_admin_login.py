"""Premium admin login page — renders, is branded, safe, and reduced-motion aware."""
import pathlib

from django.conf import settings
from django.test import TestCase

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "glitchy_admin" / "premium.css"
TPL = pathlib.Path(settings.BASE_DIR) / "templates" / "admin" / "login.html"


class AdminLoginTests(TestCase):
    def test_login_page_renders_branded(self):
        html = self.client.get("/admin/login/").content.decode()
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)
        self.assertIn("gl-login", html)
        self.assertIn("Commerce Studio", html)
        self.assertIn("gl-logo-g", html)                 # the animated monogram
        # tricolore strokes present (green + red glitch fragments)
        self.assertIn("#1a8a4b", html)
        self.assertIn("#c8322f", html)

    def test_login_has_form_and_secure_copy(self):
        html = self.client.get("/admin/login/").content.decode()
        self.assertIn('id="login-form"', html)
        self.assertIn("Secure access", html)

    def test_login_leaks_no_template_comment_or_secret(self):
        html = self.client.get("/admin/login/").content.decode()
        self.assertNotIn("{#", html)                     # no raw Django comment leaked
        self.assertNotIn("{% comment", html)
        for bad in ["PRINTIFY_CONFIG_KEY", "Bearer", "gAAAA", "token_ciphertext"]:
            self.assertNotIn(bad, html)

    def test_login_css_is_reduced_motion_safe(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("gl-login", css)
        self.assertIn("prefers-reduced-motion", css)
        # the tricolore animation exists (left-right glitch)
        self.assertIn("gl-glitch-a", css)

    def test_login_template_uses_block_comment_not_hash(self):
        # guard the multi-line comment regression (Django {# #} is single-line only)
        tpl = TPL.read_text(encoding="utf-8")
        # any {# must be closed with #} on the SAME line
        for line in tpl.splitlines():
            if "{#" in line:
                self.assertIn("#}", line, "multi-line {# #} comment leaks as text: %r" % line)
