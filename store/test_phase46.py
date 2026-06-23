"""Phase 46: de-duplicated 'made on demand' copy (FR .po corruption fix)."""
import pathlib

from django.test import TestCase
from django.conf import settings
from django.utils import translation
from django.urls import reverse

from category.models import Category
from store.models import Product, Variation

FR_PO = pathlib.Path(settings.BASE_DIR) / "locale" / "fr" / "LC_MESSAGES" / "django.po"


def _product(name="Sweet"):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    p = Product.objects.create(product_name=name, slug=name.lower(), description="x",
                               price=25, stock=9999, category=cat, is_available=True,
                               printify_provider_name="P")
    Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
    return p


class MadeOnDemandCopyTests(TestCase):
    def setUp(self):
        self.p = _product()

    def _fr_url(self):
        with translation.override("fr"):
            return self.p.get_url()

    def test_fr_pod_text_single_not_repeated(self):
        html = self.client.get(self._fr_url()).content.decode()
        # the made-on-demand lead must appear exactly once (was repeated ~13x)
        self.assertEqual(html.count("Chaque pièce est imprimée uniquement à la commande"), 1)

    def test_fr_pod_no_singular_plural_mix(self):
        html = self.client.get(self._fr_url()).content.decode()
        # the corrupted string mixed 'toujours neuve' (sing) AND 'toujours neufs' (plural)
        # in one block; the pod-card lead now uses one consistent form only.
        pod = html.split("pod-lead", 1)[-1].split("</p>", 1)[0]
        has_sing = "toujours neuve" in pod
        has_plur = "toujours neufs" in pod
        self.assertFalse(has_sing and has_plur)   # never both in the same block

    def test_en_it_render(self):
        with translation.override("en"):
            en_url = self.p.get_url()
        en = self.client.get(en_url).content.decode()
        self.assertIn("Each piece is printed only when you order", en)
        with translation.override("it"):
            it_url = self.p.get_url()
        it = self.client.get(it_url).content.decode()
        self.assertIn("pod-lead", it)

    def test_no_raw_html_or_cost_leak(self):
        html = self.client.get(self._fr_url()).content.decode()
        self.assertNotIn("base_cost", html.lower())
        self.assertNotIn("production_cost", html.lower())


class FrPoIntegrityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.po = FR_PO.read_text(encoding="utf-8")

    def test_no_concatenation_corruption(self):
        # the tell-tale "no-space period before a capital" repeats are gone
        self.assertNotIn("neufs.Imprimés", self.po)
        self.assertNotIn("neuve.Chaque", self.po)
        self.assertNotIn("neuve.Imprimés", self.po)

    def test_no_giant_msgstr(self):
        # no FR translation should be a 500+ char repeated blob
        lines = self.po.split("\n")
        n = len(lines); i = 0; longest = 0
        while i < n:
            if lines[i].startswith("msgstr "):
                v = lines[i][7:].strip()
                parts = [v[1:-1]] if v.startswith('"') else [""]
                k = i + 1
                while k < n and lines[k].startswith('"'):
                    parts.append(lines[k].strip()[1:-1]); k += 1
                longest = max(longest, len("".join(parts)))
                i = k; continue
            i += 1
        self.assertLess(longest, 500)
