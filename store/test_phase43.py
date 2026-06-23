"""Phase 43: draggable AI FAB, PDP wishlist button, cached Printify description translations."""
import json
import pathlib
from io import StringIO
from unittest import mock

from django.test import TestCase
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation as dj_translation

from category.models import Category
from store.models import Product, ProductDescriptionTranslation
from assistant import translation as tr
from assistant.providers import ProviderError

JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "assistant.js"
CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
THEME = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "theme.css"


def _product(name="Tee", description="A soft premium tee.", **kw):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description=description,
             price=25, stock=5, category=cat, is_available=True)
    d.update(kw)
    return Product.objects.create(**d)


# --------------------------------------------------------------------------- Draggable FAB
class DraggableAssistantTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = JS.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def test_js_has_pointer_drag_and_persistence(self):
        self.assertIn("pointerdown", self.js)
        self.assertIn("pointermove", self.js)
        self.assertIn("aiFabPos.v1", self.js)           # localStorage key
        self.assertIn("localStorage", self.js)

    def test_js_separates_click_from_drag(self):
        self.assertIn("dragMoved", self.js)
        self.assertIn("THRESHOLD", self.js)

    def test_css_supports_custom_position(self):
        self.assertIn(".ai-assistant.has-custom-pos", self.css)
        self.assertIn("touch-action:none", self.css)

    def test_fab_markup_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('id="aiToggle"', html)
        self.assertIn("ai-fab", html)


# --------------------------------------------------------------------------- Wishlist button
class WishlistButtonTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")
        cls.theme = THEME.read_text(encoding="utf-8")

    def test_fixed_54px_width_removed(self):
        # the root cause: a pinned 54px width that clipped translated labels
        self.assertNotIn(".pdp-actions .btn-soft{ width: 54px; }", self.theme)

    def test_wish_button_is_content_sized_flex(self):
        self.assertIn(".pdp-actions .wish-btn-pdp", self.css)
        self.assertIn("width:auto", self.css)

    def test_markup_icon_and_label_in_same_button(self):
        p = _product("Wishy")
        html = self.client.get(p.get_url()).content.decode()
        self.assertIn("wish-btn-pdp", html)
        self.assertIn("data-wishlist-label", html)
        self.assertIn("fa-heart", html)

    def test_fr_label_present(self):
        p = _product("Wishy2")
        with dj_translation.override("fr"):
            url = p.get_url()
        html = self.client.get(url).content.decode()
        self.assertTrue("Enregistrer" in html or "Enregistré" in html)


# --------------------------------------------------------------------------- Translation pipeline
class TranslationServiceTests(TestCase):
    def setUp(self):
        self.p = _product("Translatable", description="A soft premium tee. Made on demand.")

    def test_source_hash_changes_with_source(self):
        h1 = self.p.description_source_hash()
        self.p.description = "Different text entirely."
        self.assertNotEqual(h1, self.p.description_source_hash())

    def test_description_for_en_returns_source(self):
        self.assertEqual(self.p.description_for("en"), self.p.description)

    def test_cache_hit_returns_translation(self):
        ProductDescriptionTranslation.objects.create(
            product=self.p, language="it", source_hash=self.p.description_source_hash(),
            translated_text="Una t-shirt premium morbida.", status="done")
        self.assertEqual(self.p.description_for("it"), "Una t-shirt premium morbida.")

    def test_stale_hash_falls_back_to_source(self):
        ProductDescriptionTranslation.objects.create(
            product=self.p, language="fr", source_hash="oldhash0000",
            translated_text="Vieux texte.", status="done")
        # source hash no longer matches -> fall back to clean EN source
        self.assertEqual(self.p.description_for("fr"), self.p.description)

    def test_error_status_falls_back_to_source(self):
        ProductDescriptionTranslation.objects.create(
            product=self.p, language="it", source_hash=self.p.description_source_hash(),
            translated_text="", status="error", error_code="network")
        self.assertEqual(self.p.description_for("it"), self.p.description)

    @mock.patch("assistant.translation.OpenAIProvider")
    def test_translate_text_mocked_openai(self, MockProvider):
        inst = MockProvider.return_value
        inst.available.return_value = True
        inst.chat.return_value = "Una t-shirt premium morbida. Prodotta su ordinazione."
        out = tr.translate_text("A soft premium tee. Made on demand.", "it")
        self.assertIn("t-shirt premium", out)
        self.assertNotIn("<", out)   # plain text only

    @mock.patch("assistant.translation.OpenAIProvider")
    def test_missing_key_raises_safe_error(self, MockProvider):
        MockProvider.return_value.available.return_value = False
        with self.assertRaises(ProviderError):
            tr.translate_text("text", "it")

    @mock.patch("assistant.translation.translate_text", side_effect=ProviderError("network"))
    def test_api_failure_preserves_existing_translation(self, _mocked):
        good = ProductDescriptionTranslation.objects.create(
            product=self.p, language="it", source_hash="oldhash",
            translated_text="Buona vecchia traduzione.", status="done")
        res = tr.ensure_product_translation(self.p, "it", force=True, apply=True)
        self.assertEqual(res["action"], "failed")
        good.refresh_from_db()
        self.assertEqual(good.translated_text, "Buona vecchia traduzione.")  # preserved

    @mock.patch("assistant.translation.translate_text", return_value="Texte français propre.")
    def test_ensure_translation_writes_and_is_idempotent(self, _mocked):
        r1 = tr.ensure_product_translation(self.p, "fr", apply=True)
        self.assertEqual(r1["action"], "translated")
        r2 = tr.ensure_product_translation(self.p, "fr", apply=True)
        self.assertEqual(r2["action"], "cached")   # second time: cache hit, no call
        self.assertEqual(_mocked.call_count, 1)


# --------------------------------------------------------------------------- PDP multilingual
class PdpMultilingualTests(TestCase):
    def setUp(self):
        self.p = _product("MultiLang", description="English description text.")
        for lang, text in [("it", "Testo descrizione italiano."), ("fr", "Texte description français.")]:
            ProductDescriptionTranslation.objects.create(
                product=self.p, language=lang, source_hash=self.p.description_source_hash(),
                translated_text=text, status="done")

    def _localized_url(self, lang):
        with dj_translation.override(lang):
            return self.p.get_url()

    def test_pdp_en_shows_english(self):
        html = self.client.get(self._localized_url("en")).content.decode()
        self.assertIn("English description text.", html)

    def test_pdp_it_shows_italian(self):
        html = self.client.get(self._localized_url("it")).content.decode()
        self.assertIn("Testo descrizione italiano.", html)
        self.assertNotIn("English description text.", html)

    def test_pdp_fr_shows_french(self):
        html = self.client.get(self._localized_url("fr")).content.decode()
        self.assertIn("Texte description", html)

    def test_description_html_is_escaped_not_injected(self):
        # Even if a description somehow contained HTML, |linebreaksbr auto-escapes it.
        self.p.description = "Safe text <script>alert(1)</script> end"
        self.p.save()
        html = self.client.get(self.p.get_url()).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)   # never rendered live
        self.assertIn("&lt;script&gt;", html)                 # escaped instead


# --------------------------------------------------------------------------- Management command
class TranslateCommandTests(TestCase):
    def setUp(self):
        self.p = _product("CmdProd", description="Translate me please.")

    def test_dry_run_makes_no_writes(self):
        out = StringIO()
        call_command("translate_printify_descriptions", "--product-id", str(self.p.id), stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertEqual(ProductDescriptionTranslation.objects.count(), 0)

    @mock.patch("assistant.translation.translation_available", return_value=False)
    def test_apply_without_key_says_missing(self, _m):
        out = StringIO()
        call_command("translate_printify_descriptions", "--apply",
                     "--product-id", str(self.p.id), stdout=out)
        self.assertIn("missing key", out.getvalue().lower())

    def test_json_output_is_valid(self):
        out = StringIO()
        call_command("translate_printify_descriptions", "--product-id", str(self.p.id),
                     "--json", stdout=out)
        data = json.loads(out.getvalue())
        self.assertTrue(data["ok"])
        self.assertIn("stats", data)

    @mock.patch("assistant.translation.translate_text", return_value="Traduzione applicata.")
    def test_apply_mocked_writes_translation(self, _mocked):
        out = StringIO()
        call_command("translate_printify_descriptions", "--apply", "--language", "it",
                     "--product-id", str(self.p.id), stdout=out)
        self.assertIn("APPLIED", out.getvalue())
        t = ProductDescriptionTranslation.objects.get(product=self.p, language="it")
        self.assertEqual(t.translated_text, "Traduzione applicata.")


# --------------------------------------------------------------------------- AI context
class AiContextLanguageTests(TestCase):
    def test_context_uses_localized_description(self):
        from assistant.prompt import build_context
        p = _product("CtxProd", description="English ctx description.")
        ProductDescriptionTranslation.objects.create(
            product=p, language="it", source_hash=p.description_source_hash(),
            translated_text="Descrizione italiana ctx.", status="done")
        ctx_it = build_context([], [p], "it")
        self.assertIn("Descrizione italiana ctx.", ctx_it)
        ctx_en = build_context([], [p], "en")
        self.assertIn("English ctx description.", ctx_en)

    def test_context_has_no_internal_ids_or_costs(self):
        from assistant.prompt import build_context
        p = _product("CtxProd2", description="Desc.", base_cost=7.5,
                     printify_product_id="PID123")
        ctx = build_context([], [p], "en")
        self.assertNotIn("PID123", ctx)
        self.assertNotIn("7.5", ctx)
