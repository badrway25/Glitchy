"""Phase 49: no customer-facing 'Printify' category + no yellow filter hover."""
import pathlib
from io import StringIO

from django.test import TestCase
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

from category.models import Category
from store.models import Product

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"


def _cat(name="T-Shirts", slug="t-shirt", public=True):
    return Category.objects.get_or_create(slug=slug, defaults={"category_name": name, "is_public": public})[0]


# --------------------------------------------------------------- Printify category
class PrintifyCategoryTests(TestCase):
    def test_sync_fallback_never_creates_printify(self):
        from printify_integration.services import _resolve_fallback_category
        _cat("T-Shirts", "t-shirt")
        cat = _resolve_fallback_category("Printify")          # even if asked for Printify
        self.assertNotEqual(cat.slug, "printify")
        self.assertNotEqual(cat.category_name.lower(), "printify")
        self.assertFalse(Category.objects.filter(slug__iexact="printify").exists())

    def test_category_for_unmapped_returns_commercial_fallback(self):
        from printify_integration.services import _category_for
        fb = _cat("T-Shirts", "t-shirt")
        cat = _category_for({"blueprint_id": 999999}, fb, {145: "t-shirt"})   # unmapped blueprint
        self.assertEqual(cat, fb)
        self.assertFalse(Category.objects.filter(slug__iexact="printify").exists())

    def test_public_manager_excludes_technical(self):
        _cat("T-Shirts", "t-shirt", public=True)
        _cat("Printify", "printify", public=False)
        names = list(Category.public.values_list("category_name", flat=True))
        self.assertIn("T-Shirts", names)
        self.assertNotIn("Printify", names)

    def test_store_filters_exclude_non_public(self):
        _cat("T-Shirts", "t-shirt", public=True)
        _cat("Printify", "printify", public=False)
        html = self.client.get(reverse("store")).content.decode()
        # the cat-list in the filter sidebar must not list the technical category
        self.assertNotIn(">Printify<", html)
        self.assertNotIn("/printify/", html)

    def test_direct_non_public_category_page_404s(self):
        _cat("Printify", "printify", public=False)
        resp = self.client.get("/store/category/printify/")
        self.assertEqual(resp.status_code, 404)

    def test_sitemap_excludes_non_public_category(self):
        _cat("Printify", "printify", public=False)
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/category/printify/", xml)

    def test_cleanup_command_rehomes_and_deletes(self):
        target = _cat("T-Shirts", "t-shirt", public=True)
        tech = _cat("Printify", "printify", public=False)
        p = Product.objects.create(product_name="P", slug="p", description="x", price=10,
                                   stock=5, category=tech, is_available=True)
        out = StringIO()
        call_command("cleanup_printify_category", "--apply", "--json", stdout=out)
        import json
        data = json.loads(out.getvalue())
        self.assertEqual(data["reassigned"], 1)
        self.assertEqual(data["deleted"], 1)
        p.refresh_from_db()
        self.assertEqual(p.category, target)                  # product re-homed, not deleted
        self.assertFalse(Category.objects.filter(slug__iexact="printify").exists())

    def test_cleanup_dry_run_changes_nothing(self):
        _cat("T-Shirts", "t-shirt", public=True)
        _cat("Printify", "printify", public=False)
        call_command("cleanup_printify_category", stdout=StringIO())
        self.assertTrue(Category.objects.filter(slug__iexact="printify").exists())


# --------------------------------------------------------------- Filter hover
class FilterHoverTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_chip_hover_not_gold(self):
        # the source rule must no longer use the gold accent on hover
        self.assertNotIn(".chip-opt:hover span{border-color:var(--accent);}", self.css)
        self.assertIn(".chip-opt:hover span{border-color:rgba(28,26,23,.30);}", self.css)

    def test_no_invalid_border_strong_as_color(self):
        # --border-strong is a shorthand (1px solid ...), never valid as border-color
        self.assertNotIn("border-color:var(--border-strong", self.css)

    def test_filter_accent_color_not_gold_either_theme(self):
        self.assertIn(".filter-form .chip-opt input{accent-color:var(--primary)", self.css)
        # dark mode no longer reverts to gold accent
        dark = self.css.split('Root cause: native checkbox', 1)[-1]
        self.assertNotIn(':root[data-theme="dark"] .filter-form .rating-opt input,\n'
                         ':root[data-theme="dark"] .filter-form .toggle-opt input{accent-color:var(--accent);}',
                         self.css)

    def test_store_page_renders(self):
        _cat("T-Shirts", "t-shirt")
        self.assertEqual(self.client.get(reverse("store")).status_code, 200)
