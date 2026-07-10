"""Tests for the build_color_image_maps command and the OpenAI vision matcher.

Everything is offline: the Printify client and OpenAI provider are faked/mocked.
The command is dry-run by default, --openai needs --apply, and a missing key
degrades cleanly to the deterministic/heuristic stages.
"""
import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from category.models import Category
from store.models import Product, ProductColorImage, ProductImage, Variation

from printify_integration.ai_match import classify_image_color


def _product(name):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                  price=20, stock=5, category=cat)


def _setup_partial_product():
    """Black resolvable from variant titles; Red and Green have no data anywhere:
    with TWO unresolved colours the elimination heuristic stays out (ambiguous),
    so their rows stay empty — exactly the case the AI stage exists for."""
    p = _product("Cmd Tee")
    Variation.objects.create(product=p, variation_category="color", variation_value="Black",
                             printify_variant_id="1", printify_title="Black / M")
    Variation.objects.create(product=p, variation_category="color", variation_value="Red")
    Variation.objects.create(product=p, variation_category="color", variation_value="Green")
    ProductImage.objects.create(product=p, printify_variant_ids="1,2",
                                printify_src="https://images.example/one.jpg", sort_order=0)
    ProductImage.objects.create(product=p, printify_variant_ids="",
                                printify_src="https://images.example/mystery1.jpg", sort_order=1)
    ProductImage.objects.create(product=p, printify_variant_ids="",
                                printify_src="https://images.example/mystery2.jpg", sort_order=2)
    return p


class CommandDryRunApplyTests(TestCase):
    def test_dry_run_writes_nothing(self):
        _setup_partial_product()
        out = StringIO()
        call_command("build_color_image_maps", stdout=out)
        self.assertEqual(ProductColorImage.objects.count(), 0)
        self.assertIn("DRY-RUN", out.getvalue())

    def test_apply_writes_rows(self):
        p = _setup_partial_product()
        out = StringIO()
        call_command("build_color_image_maps", "--apply", stdout=out)
        black = ProductColorImage.objects.get(product=p, color_value="black")
        self.assertEqual(black.source, ProductColorImage.SOURCE_DETERMINISTIC)
        self.assertIn("APPLIED", out.getvalue())

    def test_product_id_filter(self):
        p1 = _setup_partial_product()
        p2 = _product("Other Tee")
        Variation.objects.create(product=p2, variation_category="color",
                                 variation_value="Blue")
        ProductImage.objects.create(product=p2, printify_variant_ids="9",
                                    printify_src="https://images.example/b.jpg")
        call_command("build_color_image_maps", "--apply",
                     f"--product-id={p2.id}", stdout=StringIO())
        self.assertFalse(ProductColorImage.objects.filter(product=p1).exists())
        self.assertTrue(ProductColorImage.objects.filter(product=p2).exists())

    def test_json_output_is_safe_and_parsable(self):
        _setup_partial_product()
        out = StringIO()
        call_command("build_color_image_maps", "--json", stdout=out)
        data = json.loads(out.getvalue())
        self.assertIn("totals", data)
        self.assertFalse(data["totals"]["applied"])


@override_settings(AI_API_KEY="")
class CommandOpenAITests(TestCase):
    def test_openai_without_apply_is_ignored(self):
        _setup_partial_product()
        with mock.patch("printify_integration.management.commands."
                        "build_color_image_maps.classify_image_color") as classify:
            out = StringIO()
            call_command("build_color_image_maps", "--openai", stdout=out)
            classify.assert_not_called()
            self.assertIn("--openai ignored in dry-run", out.getvalue())

    def test_openai_missing_key_degrades_cleanly(self):
        p = _setup_partial_product()
        out = StringIO()
        call_command("build_color_image_maps", "--apply", "--openai", stdout=out)
        self.assertIn("OpenAI not configured", out.getvalue())
        # deterministic stage still ran
        self.assertTrue(ProductColorImage.objects.filter(
            product=p, color_value="black").exclude(image_ids="").exists())

    def test_openai_fills_unresolved_rows(self):
        p = _setup_partial_product()
        fake_provider = mock.Mock()
        fake_provider.available.return_value = True
        with mock.patch("assistant.providers.OpenAIProvider",
                        return_value=fake_provider), \
             mock.patch("printify_integration.management.commands."
                        "build_color_image_maps.classify_image_color",
                        return_value="red") as classify:
            call_command("build_color_image_maps", "--apply", "--openai",
                         stdout=StringIO())
        red = ProductColorImage.objects.get(product=p, color_value="red")
        self.assertEqual(red.source, ProductColorImage.SOURCE_OPENAI)
        self.assertLess(red.confidence, 1.0)
        self.assertEqual(len(red.image_id_list()), 2)     # both mystery images
        self.assertEqual(classify.call_count, 2)          # persisted -> no re-asking
        black = ProductColorImage.objects.get(product=p, color_value="black")
        self.assertEqual(black.source, ProductColorImage.SOURCE_DETERMINISTIC)
        # the model never said "green" -> green stays honestly unresolved
        green = ProductColorImage.objects.get(product=p, color_value="green")
        self.assertEqual(green.image_ids, "")

    def test_ai_stage_never_touches_manual_rows(self):
        """An admin-pinned manual row (even deliberately EMPTY, to force the
        default-gallery fallback) must survive --openai untouched."""
        p = _setup_partial_product()
        # pin red as manual-empty BEFORE the run
        ProductColorImage.objects.create(
            product=p, color_value="red", image_ids="",
            source=ProductColorImage.SOURCE_MANUAL, confidence=1.0)
        fake_provider = mock.Mock()
        fake_provider.available.return_value = True
        with mock.patch("assistant.providers.OpenAIProvider",
                        return_value=fake_provider), \
             mock.patch("printify_integration.management.commands."
                        "build_color_image_maps.classify_image_color",
                        return_value="red") as classify:
            call_command("build_color_image_maps", "--apply", "--openai",
                         stdout=StringIO())
        red = ProductColorImage.objects.get(product=p, color_value="red")
        self.assertEqual(red.source, ProductColorImage.SOURCE_MANUAL)
        self.assertEqual(red.image_ids, "")
        # red was not offered as a choice: only green remained classifiable, and
        # the model kept answering "red" -> nothing was persisted for green either
        green = ProductColorImage.objects.get(product=p, color_value="green")
        self.assertEqual(green.image_ids, "")
        self.assertTrue(classify.called)

    def test_json_stdout_is_pure_json_even_with_notices(self):
        _setup_partial_product()
        out, err = StringIO(), StringIO()
        # --openai without a key triggers the 'not configured' notice: must go to stderr
        call_command("build_color_image_maps", "--apply", "--openai", "--json",
                     stdout=out, stderr=err)
        data = json.loads(out.getvalue())        # would raise if a notice leaked in
        self.assertTrue(data["totals"]["applied"])
        self.assertIn("OpenAI not configured", err.getvalue())

    def test_ai_budget_caps_calls(self):
        p = _setup_partial_product()
        fake_provider = mock.Mock()
        fake_provider.available.return_value = True
        with mock.patch("assistant.providers.OpenAIProvider",
                        return_value=fake_provider), \
             mock.patch("printify_integration.management.commands."
                        "build_color_image_maps.classify_image_color",
                        return_value=None) as classify:
            call_command("build_color_image_maps", "--apply", "--openai",
                         "--max-ai-calls=1", stdout=StringIO())
        self.assertEqual(classify.call_count, 1)
        self.assertEqual(ProductColorImage.objects.get(
            product=p, color_value="red").image_ids, "")


class CommandLiveRefetchTests(TestCase):
    def test_live_uses_refetched_payload(self):
        p = _product("Live Tee")
        p.printify_product_id = "pp_9"
        p.save()
        Variation.objects.create(product=p, variation_category="color",
                                 variation_value="Black")
        Variation.objects.create(product=p, variation_category="color",
                                 variation_value="White")
        img_b = ProductImage.objects.create(product=p, printify_variant_ids="1",
                                            printify_src="https://images.example/b.jpg",
                                            sort_order=0)
        ProductImage.objects.create(product=p, printify_variant_ids="3",
                                    printify_src="https://images.example/w.jpg",
                                    sort_order=1)
        payload = {
            "options": [{"type": "color", "values": [
                {"id": 10, "title": "Black"}, {"id": 11, "title": "White"}]}],
            "variants": [{"id": 1, "options": [10]}, {"id": 3, "options": [11]}],
        }
        fake_client = mock.Mock()
        fake_client.get_product.return_value = payload
        with mock.patch("printify_integration.management.commands."
                        "build_color_image_maps._resolve_client",
                        return_value=fake_client):
            call_command("build_color_image_maps", "--apply", "--live",
                         stdout=StringIO())
        fake_client.get_product.assert_called_once_with("pp_9")
        black = ProductColorImage.objects.get(product=p, color_value="black")
        self.assertEqual(black.image_id_list(), [img_b.id])
        self.assertIn("payload", black.detail)


class ClassifyImageColorTests(TestCase):
    def _provider(self, answer=None, error=False, available=True):
        from assistant.providers import ProviderError
        provider = mock.Mock()
        provider.available.return_value = available
        if error:
            provider.chat.side_effect = ProviderError("network")
        else:
            provider.chat.return_value = answer
        return provider

    def test_valid_answer_returned_lowercase(self):
        provider = self._provider("Black")
        self.assertEqual(classify_image_color("https://x/i.jpg", ["Black", "White"],
                                              provider=provider), "black")

    def test_unknown_answer_returns_none(self):
        provider = self._provider("UNKNOWN")
        self.assertIsNone(classify_image_color("https://x/i.jpg", ["Black"],
                                               provider=provider))

    def test_hallucinated_color_discarded(self):
        provider = self._provider("Fuchsia")
        self.assertIsNone(classify_image_color("https://x/i.jpg", ["Black", "White"],
                                               provider=provider))

    def test_network_error_fails_safe_with_retry(self):
        provider = self._provider(error=True)
        self.assertIsNone(classify_image_color("https://x/i.jpg", ["Black"],
                                               provider=provider))
        self.assertEqual(provider.chat.call_count, 2)     # one retry

    def test_unavailable_provider_short_circuits(self):
        provider = self._provider(available=False)
        self.assertIsNone(classify_image_color("https://x/i.jpg", ["Black"],
                                               provider=provider))
        provider.chat.assert_not_called()
