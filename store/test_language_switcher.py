"""Phase 57: premium language switcher — names only (no EN/IT/FR codes),
flag-inspired backgrounds, i18n, a11y. No real data."""
import pathlib

from django.conf import settings
from django.test import TestCase

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"


class LanguageSwitcherTests(TestCase):
    def _html(self, path="/"):
        return self.client.get(path).content.decode()

    def test_switcher_renders(self):
        html = self._html("/")
        self.assertIn("lang-switcher", html)
        self.assertIn("lang-name", html)
        self.assertIn('name="language"', html)  # set_language form intact

    def test_no_language_codes_visible(self):
        """No 'EN'/'IT'/'FR' code chips or the old lang-code badge."""
        html = self._html("/")
        self.assertNotIn("lang-code", html)        # old code badge removed
        self.assertNotIn("(EN)", html)
        self.assertNotIn("(IT)", html)
        self.assertNotIn("(FR)", html)

    def test_options_have_flag_classes(self):
        html = self._html("/")
        self.assertIn("lang-opt lang-en", html)
        self.assertIn("lang-opt lang-it", html)
        self.assertIn("lang-opt lang-fr", html)

    def test_current_language_marked(self):
        html = self._html("/")  # English (no prefix)
        self.assertIn("lang-en active", html)
        self.assertIn('aria-current="true"', html)

    def test_button_shows_native_name_en(self):
        html = self._html("/")
        self.assertIn("English", html)

    def test_button_shows_native_name_it(self):
        html = self._html("/it/")
        self.assertIn("Italiano", html)
        self.assertIn("lang-it active", html)
        self.assertIn("Scegli la lingua", html)  # header localized IT

    def test_button_shows_native_name_fr(self):
        html = self._html("/fr/")
        self.assertIn("Français", html)
        self.assertIn("lang-fr active", html)
        self.assertIn("Choisir la langue", html)  # header localized FR

    def test_header_localized_en(self):
        self.assertIn("Choose language", self._html("/"))

    def test_accessibility_markup(self):
        html = self._html("/")
        self.assertIn('aria-label="Change language"', html)
        self.assertIn('aria-haspopup="true"', html)

    def test_css_flag_backgrounds_present(self):
        """Each language has a FULL-WIDTH flag-inspired background (not a left bar)."""
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lang-switcher .lang-opt.lang-it", css)
        self.assertIn(".lang-switcher .lang-opt.lang-fr", css)
        self.assertIn(".lang-switcher .lang-opt.lang-en", css)
        # dark-mode variants keep the bands legible
        self.assertIn(':root[data-theme="dark"] .lang-switcher .lang-opt.lang-it', css)

    def test_css_flag_persists_on_hover(self):
        """Hover must NOT wipe the flag (theme.css forces .dropdown-item:hover bg)."""
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".lang-switcher .lang-opt.lang-it:hover", css)
        self.assertIn(".lang-switcher .lang-opt.lang-fr:hover", css)
        self.assertIn(".lang-switcher .lang-opt.lang-en:hover", css)
