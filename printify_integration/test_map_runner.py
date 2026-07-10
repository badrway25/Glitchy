"""Tests for the shared mapping runner (printify_integration/map_runner.py)."""
from unittest import mock

from django.test import TestCase, override_settings

from category.models import Category
from store.models import (Product, ProductColorImage, ProductColorImageMapRun,
                          ProductImage, Variation)

from printify_integration.map_runner import run_color_image_mapping


def _product(name, with_map_data=True):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               price=20, stock=5, category=cat)
    Variation.objects.create(product=p, variation_category="color",
                             variation_value="Black",
                             printify_variant_id="1" if with_map_data else None)
    if not with_map_data:
        # a second data-less colour keeps every heuristic (single-colour,
        # elimination) out — the product stays genuinely unresolved
        Variation.objects.create(product=p, variation_category="color",
                                 variation_value="Red")
    ProductImage.objects.create(
        product=p, printify_variant_ids="1,2" if with_map_data else "",
        printify_src=f"https://img.example/{p.slug}.jpg")
    return p


class RunnerCoreTests(TestCase):
    def test_dry_run_writes_no_maps_but_records_history(self):
        _product("Runner Tee")
        result = run_color_image_mapping(apply=False, requested_by="tester")
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(ProductColorImage.objects.count(), 0)   # rolled back
        run = ProductColorImageMapRun.objects.get(pk=result["run_id"])
        self.assertEqual(run.mode, "dry_run")
        self.assertEqual(run.created_by, "tester")
        self.assertEqual(run.status, ProductColorImageMapRun.STATUS_SUCCEEDED)
        self.assertEqual(run.colors_resolved, 1)
        self.assertGreaterEqual(len(run.safe_summary_json["rows"]), 1)

    def test_apply_writes_maps(self):
        p = _product("Apply Tee")
        result = run_color_image_mapping(apply=True)
        self.assertEqual(result["colors_resolved"], 1)
        row = ProductColorImage.objects.get(product=p, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_DETERMINISTIC)

    def test_products_changed_zero_on_identical_rerun(self):
        _product("Stable Tee")
        run_color_image_mapping(apply=True)
        second = run_color_image_mapping(apply=True)
        self.assertEqual(second["products_changed"], 0)

    def test_only_unresolved_scopes_out_resolved_products(self):
        resolved = _product("Resolved Tee")
        unresolved = _product("Pending Tee", with_map_data=False)
        run_color_image_mapping(apply=True)   # resolves the first, leaves the second
        result = run_color_image_mapping(apply=True, only_unresolved=True)
        slugs = {line["product"] for line in result["product_lines"]}
        self.assertIn(unresolved.slug, slugs)
        self.assertNotIn(resolved.slug, slugs)

    def test_product_cap_warns_and_truncates(self):
        for i in range(3):
            _product(f"Cap Tee {i}")
        result = run_color_image_mapping(apply=False, product_cap=2)
        self.assertEqual(result["products_scanned"], 2)
        self.assertTrue(any("capped" in w for w in result["warnings"]))

    def test_manual_rows_counted_and_preserved(self):
        p = _product("Pin Tee")
        ProductColorImage.objects.create(
            product=p, color_value="black", image_ids="777",
            source=ProductColorImage.SOURCE_MANUAL, confidence=1.0)
        result = run_color_image_mapping(apply=True)
        self.assertEqual(result["manual_preserved"], 1)
        row = ProductColorImage.objects.get(product=p, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_MANUAL)
        self.assertEqual(row.image_ids, "777")

    @override_settings(AI_API_KEY="")
    def test_openai_unavailable_degrades_with_warning(self):
        _product("NoKey Tee")
        result = run_color_image_mapping(apply=True, use_openai=True)
        self.assertFalse(result["use_openai"])
        self.assertTrue(any("OpenAI not configured" in w for w in result["warnings"]))

    def test_openai_requires_apply(self):
        _product("DryAI Tee")
        with mock.patch("printify_integration.map_runner.classify_image_color") as c:
            result = run_color_image_mapping(apply=False, use_openai=True)
            c.assert_not_called()
        self.assertTrue(any("requires Apply" in w for w in result["warnings"]))

    def test_summary_contains_no_secret_material(self):
        _product("Safe Tee")
        result = run_color_image_mapping(apply=True)
        run = ProductColorImageMapRun.objects.get(pk=result["run_id"])
        blob = str(run.safe_summary_json) + str(result)
        for needle in ("sk-", "Bearer", "token_ciphertext", "api_key"):
            self.assertNotIn(needle, blob, needle)

    def test_broken_product_marks_partial_not_failed(self):
        _product("Good Tee")
        _product("Bad Tee")
        real = run_color_image_mapping  # keep a reference for sanity
        with mock.patch("printify_integration.map_runner.rebuild_color_image_map",
                        side_effect=[{"colors": 1, "resolved": 1, "sources": {}},
                                     RuntimeError("boom")]):
            result = real(apply=False)
        self.assertEqual(result["status"], ProductColorImageMapRun.STATUS_PARTIAL)
        self.assertEqual(result["products_scanned"], 1)
        self.assertTrue(any("failed" in w for w in result["warnings"]))
