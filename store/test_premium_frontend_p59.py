"""Phase 59: premium frontend refinement + DB readiness safety.

Covers the search pill markup, the new "How it works" section (EN/IT/FR), the hero
rotator, centralized container width, no nested forms, premium CSS tokens (serif
font + focus states), and the safe DB readiness audit (no PII, masked db name).
"""
import io
import json
import pathlib
import re

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

BASE = pathlib.Path(settings.BASE_DIR)
SRC = BASE / "greatkart" / "static"
CSS = SRC / "css" / "premium.css"
BASE_HTML = BASE / "templates" / "base.html"


def _no_nested_forms(html: str) -> bool:
    """True iff no <form> opens while another <form> is still open."""
    depth = 0
    for tok in re.findall(r"<\s*/?\s*form\b", html, re.I):
        if "/" in tok:
            depth = max(0, depth - 1)
        else:
            if depth > 0:
                return False
            depth += 1
    return True


class PremiumFrontendP59Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from category.models import Category
        for name, slug in [("Shirts", "shirts"), ("T Shirt", "t-shirt"), ("Jackets", "jackets")]:
            Category.objects.get_or_create(slug=slug, defaults={"category_name": name})

    def _html(self, path="/"):
        return self.client.get(path).content.decode()

    # -- search pill ----------------------------------------------------------
    def test_search_pill_markup(self):
        html = self._html("/")
        self.assertIn("searchbar-xl", html)
        self.assertEqual(html.count('class="search-go"'), 1)
        self.assertIn('name="keyword"', html)

    def test_search_css_is_integrated_button(self):
        css = CSS.read_text(encoding="utf-8")
        # flush, full-height button with matching right pill radius (no gap defect)
        self.assertIn(".search-go", css)
        self.assertIn("border-radius:0 var(--radius-pill) var(--radius-pill) 0", css.replace(" ", " "))
        self.assertIn(".searchbar-xl:focus-within .search-go", css)

    # -- new section ----------------------------------------------------------
    def test_how_it_works_renders(self):
        html = self._html("/")
        self.assertEqual(html.count("hiw-step"), 3)
        self.assertIn("How Glitchy works", html)
        self.assertIn("Choose your style", html)
        self.assertIn("Delivered with an estimate", html)

    def test_how_it_works_localized(self):
        it = self._html("/it/")
        self.assertIn("Come funziona Glitchy", it)
        self.assertIn("Scegli il tuo stile", it)
        fr = self._html("/fr/")
        self.assertIn("Comment fonctionne Glitchy", fr)
        self.assertIn("Choisissez votre style", fr)

    # -- rotator --------------------------------------------------------------
    def test_hero_rotator_present(self):
        html = self._html("/")
        self.assertIn("data-rotator", html)
        self.assertEqual(html.count('class="rot', ), html.count('class="rot'))  # sanity
        self.assertGreaterEqual(html.count('class="rot'), 3)

    # -- container width centralized -----------------------------------------
    def test_container_width_centralized(self):
        html = self._html("/")
        self.assertNotIn("max-width:1280px", html)
        self.assertIn("max-width:var(--container-max)", html)

    def test_container_token_defined(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--container-max:1320px", css.replace(" ", ""))

    # -- no nested forms ------------------------------------------------------
    def test_no_nested_forms_home_and_store(self):
        self.assertTrue(_no_nested_forms(self._html("/")))
        self.assertTrue(_no_nested_forms(self._html("/store/")))

    # -- premium tokens -------------------------------------------------------
    def test_premium_font_and_palette(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("Fraunces", css)               # premium serif display
        self.assertIn("--primary-2:#2a2824", css.replace(" ", ""))  # soft (not #000)
        base = BASE_HTML.read_text(encoding="utf-8")
        self.assertIn("Fraunces", base)              # webfont loaded

    def test_unified_focus_states(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(":focus-visible", css)
        self.assertIn(".hiw", css)

    # -- DB readiness audit safety -------------------------------------------
    def test_db_readiness_audit_safe(self):
        out = io.StringIO()
        call_command("db_readiness_audit", "--json", stdout=out)
        data = json.loads(out.getvalue())
        self.assertIn("counts", data)
        self.assertFalse(data["pii_included"])
        # db name must be masked (contains a mask char, not a full readable path)
        self.assertIn("*", data["database_masked"])
        self.assertNotIn("/", data["database_masked"])
        self.assertNotIn("\\", data["database_masked"])
        # counts are integers (or None), never row content
        for v in data["counts"].values():
            self.assertTrue(v is None or isinstance(v, int))
