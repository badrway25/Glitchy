"""Phase 42: dark mode visibility/contrast regressions (CSS-level guards)."""
import pathlib

from django.test import TestCase
from django.conf import settings
from django.urls import reverse

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"


class DarkModeTokenTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_dark_theme_block_exists(self):
        self.assertIn(':root[data-theme="dark"]', self.css)

    def test_primary_ctas_get_dark_text_in_dark_mode(self):
        # --primary inverts to a LIGHT surface in dark mode, so CTA text must be dark
        self.assertIn(':root[data-theme="dark"] .btn-primary', self.css)
        self.assertIn(':root[data-theme="dark"] .summary-cta', self.css)

    def test_ai_fab_dark_text_in_dark_mode(self):
        # the "Ask" floating button was white-on-light (invisible) — must be fixed
        self.assertIn(':root[data-theme="dark"] .ai-fab', self.css)
        self.assertIn(':root[data-theme="dark"] .ai-fab-badge', self.css)

    def test_brand_bands_use_dark_surface_in_dark_mode(self):
        # announce bar + trust strip were light-on-light (invisible)
        for band in (".announce-bar", ".lux-strip", ".faq-cta"):
            self.assertIn(band, self.css)
        # they must be remapped under the dark theme
        dark_section = self.css.split(':root[data-theme="dark"]', 1)[1]
        self.assertIn(".lux-strip", dark_section)
        self.assertIn(".announce-bar", dark_section)

    def test_active_category_and_chips_dark_text(self):
        self.assertIn(':root[data-theme="dark"] .cat-item.active', self.css)
        self.assertIn("chip-opt input:checked", self.css)

    def test_rating_pill_and_stars_readable_in_dark(self):
        self.assertIn(':root[data-theme="dark"] .pdp-pill', self.css)
        self.assertIn(':root[data-theme="dark"] .rating-stars-fill', self.css)


class ThemeToggleMarkupTests(TestCase):
    def test_theme_toggle_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("data-theme-toggle", html)

    def test_dark_logo_variant_present(self):
        html = self.client.get(reverse("home")).content.decode()
        # the white logo for dark theme must exist in the navbar
        self.assertIn("logo-glitchy-nav-light.png", html)
