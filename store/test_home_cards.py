"""Home trust cards (Phase 76) — structure regression tests."""
import pathlib

from django.conf import settings
from django.test import TestCase


class HomeCardTests(TestCase):
    def test_home_renders_cards_with_readmore_and_dialog(self):
        html = self.client.get("/").content.decode()
        self.assertIn("data-lux-features", html)
        self.assertIn("data-lux-more", html)                 # read-more trigger
        self.assertIn('id="luxFeatureDialog"', html)         # detail dialog
        self.assertIn("home-features.js", html)

    def test_cards_css_equalheight_and_clamp_present(self):
        css = (pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css").read_text(encoding="utf-8")
        self.assertIn(".lux-feature{background:", css)
        self.assertIn("min-height:100%", css)                # equal-height flex
        self.assertIn(".lux-feature.lux-clamp p{", css)      # line-clamp when JS active
        self.assertIn("dialog.lux-dialog", css)

    def test_home_features_js_is_progressive_and_reduced_motion_safe(self):
        js = (pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "home-features.js").read_text(encoding="utf-8")
        self.assertIn("showModal", js)                       # native <dialog>
        self.assertIn("lux-overflow", js)                    # reveal trigger only on overflow
