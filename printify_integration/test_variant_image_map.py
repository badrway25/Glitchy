"""Tests for the colour → image mapping builder (printify_integration/variant_images.py).

The builder resolves which gallery images belong to each colour variation, with a
strict priority: deterministic payload data > deterministic DB variant titles >
local heuristics. OpenAI is NOT part of this module (it lives in the management
command as a last-resort classifier) — nothing here touches the network.
"""
from django.test import TestCase

from category.models import Category
from store.models import Product, ProductImage, ProductColorImage, Variation

from printify_integration.variant_images import rebuild_color_image_map


def _product(name="Mars Tee"):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    return Product.objects.create(
        product_name=name, slug=name.lower().replace(" ", "-"),
        price=25, stock=10, category=cat,
    )


def _image(product, variant_ids="", src="", sort_order=0, is_default=False):
    return ProductImage.objects.create(
        product=product, printify_variant_ids=variant_ids,
        printify_src=src, sort_order=sort_order, is_default=is_default,
    )


def _variation(product, category, value, variant_id=None, title=""):
    return Variation.objects.create(
        product=product, variation_category=category, variation_value=value,
        printify_variant_id=variant_id, printify_title=title,
    )


PAYLOAD = {
    "options": [
        {"type": "color", "values": [
            {"id": 10, "title": "Black"},
            {"id": 11, "title": "White"},
        ]},
        {"type": "size", "values": [
            {"id": 20, "title": "S"},
            {"id": 21, "title": "M"},
        ]},
    ],
    "variants": [
        {"id": 1, "options": [10, 20], "is_enabled": True},   # Black / S
        {"id": 2, "options": [10, 21], "is_enabled": True},   # Black / M
        {"id": 3, "options": [11, 20], "is_enabled": True},   # White / S
        {"id": 4, "options": [11, 21], "is_enabled": False},  # White / M (disabled)
    ],
}


class PayloadDeterministicTests(TestCase):
    def setUp(self):
        self.product = _product()
        _variation(self.product, "color", "Black")
        _variation(self.product, "color", "White")
        self.img_black = _image(self.product, "1,2", sort_order=0, is_default=True)
        self.img_white = _image(self.product, "3,4", sort_order=1)
        self.img_shared = _image(self.product, "1,2,3,4", sort_order=2)

    def test_payload_maps_each_color_exactly(self):
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        # colour-specific images first, shared images appended after
        self.assertEqual(black.image_id_list(), [self.img_black.id, self.img_shared.id])
        self.assertEqual(white.image_id_list(), [self.img_white.id, self.img_shared.id])
        self.assertEqual(black.primary_image_id, self.img_black.id)
        self.assertEqual(white.primary_image_id, self.img_white.id)
        for row in (black, white):
            self.assertEqual(row.source, ProductColorImage.SOURCE_DETERMINISTIC)
            self.assertEqual(row.confidence, 1.0)

    def test_disabled_variants_still_count_for_matching(self):
        # img_white carries id 4 (disabled White/M) — matching must still work
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        self.assertIn(self.img_white.id, white.image_id_list())

    def test_idempotent_rebuild(self):
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        first = list(ProductColorImage.objects.filter(product=self.product)
                     .order_by("color_value").values_list("color_value", "image_ids"))
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        second = list(ProductColorImage.objects.filter(product=self.product)
                      .order_by("color_value").values_list("color_value", "image_ids"))
        self.assertEqual(first, second)
        self.assertEqual(ProductColorImage.objects.filter(product=self.product).count(), 2)

    def test_removed_color_row_deleted(self):
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        Variation.objects.filter(product=self.product, variation_value="White").delete()
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        self.assertFalse(ProductColorImage.objects.filter(
            product=self.product, color_value="white").exists())


class ColorRowVidDeterministicTests(TestCase):
    """No payload: the reliable DB pairing is the COLOUR row's printify_variant_id
    (set at creation from a variant of that colour, never rewritten). Modelled on the
    real 'sweet-dreams' product where size-row TITLES are scrambled by resyncs."""

    def setUp(self):
        self.product = _product()
        _variation(self.product, "color", "White", variant_id="38191", title="White / 5XL")
        _variation(self.product, "color", "Dark Heather", variant_id="63300",
                   title="Dark Heather / 5XL")
        _variation(self.product, "color", "Black")   # manual row, no variant data
        # size rows: ids from the FIRST sync pass, titles from the LAST -> scrambled
        _variation(self.product, "size", "L", variant_id="63300", title="White / L")
        _variation(self.product, "size", "XL", variant_id="38205", title="Dark Heather / XL")
        self.img_white = _image(self.product, "38191,38205,38219", sort_order=0)
        self.img_dark = _image(self.product, "63300,63295,63290", sort_order=1)

    def test_color_row_vids_partition_gallery_despite_scrambled_titles(self):
        rebuild_color_image_map(self.product)
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        dark = ProductColorImage.objects.get(product=self.product, color_value="dark heather")
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(white.image_id_list(), [self.img_white.id])
        self.assertEqual(dark.image_id_list(), [self.img_dark.id])
        self.assertEqual(white.source, ProductColorImage.SOURCE_DETERMINISTIC)
        self.assertEqual(black.image_ids, "")        # honestly unresolved, no invention


class TitleVoteHeuristicTests(TestCase):
    """Without colour-row vids, variant titles act as a WEAK majority vote."""

    def setUp(self):
        self.product = _product()
        _variation(self.product, "color", "Black")
        _variation(self.product, "color", "White")
        _variation(self.product, "size", "S", variant_id="1", title="Black / S")
        _variation(self.product, "size", "M", variant_id="3", title="White / S")
        self.img_black = _image(self.product, "1,2", sort_order=0)
        self.img_white = _image(self.product, "3,4", sort_order=1)

    def test_title_votes_partition_gallery_as_heuristic(self):
        rebuild_color_image_map(self.product)
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        self.assertEqual(black.image_id_list(), [self.img_black.id])
        self.assertEqual(white.image_id_list(), [self.img_white.id])
        self.assertEqual(black.source, ProductColorImage.SOURCE_HEURISTIC)
        self.assertIn("title", black.detail)
        self.assertLess(black.confidence, 1.0)

    def test_reversed_title_order_still_resolves(self):
        Variation.objects.filter(product=self.product, variation_category="size").delete()
        _variation(self.product, "size", "S", variant_id="1", title="S / Black")
        _variation(self.product, "size", "M", variant_id="3", title="S / White")
        rebuild_color_image_map(self.product)
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(black.image_id_list(), [self.img_black.id])

    def test_scrambled_titles_abort_the_vote(self):
        """When one mockup group receives title votes for TWO colours the titles are
        provably scrambled — the vote must abort and leave rows empty rather than
        guess (real resync behaviour: size-row titles are last-write-wins)."""
        Variation.objects.filter(product=self.product, variation_category="size").delete()
        _variation(self.product, "size", "S", variant_id="1", title="White / S")
        _variation(self.product, "size", "M", variant_id="2", title="Black / M")
        # img_black carries ids 1 AND 2 -> votes for both colours -> inconsistent
        rebuild_color_image_map(self.product)
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        self.assertEqual(black.image_ids, "")
        self.assertEqual(white.image_ids, "")

    def test_contradictory_variant_id_dropped(self):
        """The same variant id titled with two different colours on two rows is
        dropped from the vote; the leftover colour is then resolved by elimination
        (last unmatched colour), NOT by the poisoned title."""
        Variation.objects.filter(product=self.product, variation_category="size").delete()
        _variation(self.product, "size", "S", variant_id="1", title="Black / S")
        _variation(self.product, "size", "M", variant_id="1", title="White / M")
        _variation(self.product, "size", "L", variant_id="3", title="White / L")
        rebuild_color_image_map(self.product)
        white = ProductColorImage.objects.get(product=self.product, color_value="white")
        black = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(white.image_id_list(), [self.img_white.id])   # vid 3 still counts
        self.assertIn("title", white.detail)
        self.assertEqual(black.image_id_list(), [self.img_black.id])   # via elimination
        self.assertIn("elimination", black.detail)


class HeuristicTests(TestCase):
    def test_single_color_product_takes_all_images(self):
        product = _product("Solo Tee")
        _variation(product, "color", "Navy")
        img1 = _image(product, "7,8", sort_order=0)
        img2 = _image(product, "7,8", sort_order=1)
        rebuild_color_image_map(product)
        row = ProductColorImage.objects.get(product=product, color_value="navy")
        self.assertEqual(row.image_id_list(), [img1.id, img2.id])
        self.assertEqual(row.source, ProductColorImage.SOURCE_HEURISTIC)
        self.assertLess(row.confidence, 1.0)

    def test_filename_match(self):
        product = _product("File Tee")
        _variation(product, "color", "Black")
        _variation(product, "color", "Dark Heather")
        img_b = _image(product, src="https://img.example/mock/black-front.jpg", sort_order=0)
        img_dh = _image(product, src="https://img.example/mock/dark-heather-back.jpg", sort_order=1)
        rebuild_color_image_map(product)
        black = ProductColorImage.objects.get(product=product, color_value="black")
        dh = ProductColorImage.objects.get(product=product, color_value="dark heather")
        self.assertEqual(black.image_id_list(), [img_b.id])
        self.assertEqual(dh.image_id_list(), [img_dh.id])
        self.assertEqual(black.source, ProductColorImage.SOURCE_HEURISTIC)

    def test_elimination_assigns_remaining_group(self):
        product = _product("Elim Tee")
        _variation(product, "color", "White")
        _variation(product, "color", "Black")
        _variation(product, "size", "S", variant_id="3", title="White / S")
        img_w = _image(product, "3,4", sort_order=0)
        img_unknown = _image(product, "8,9", sort_order=1)
        rebuild_color_image_map(product)
        black = ProductColorImage.objects.get(product=product, color_value="black")
        self.assertEqual(black.image_id_list(), [img_unknown.id])
        self.assertEqual(black.source, ProductColorImage.SOURCE_HEURISTIC)
        self.assertIn("elimination", black.detail)

    def test_elimination_with_multiple_unknown_images(self):
        product = _product("Mystery Tee")
        _variation(product, "color", "Black")
        _variation(product, "color", "White")
        _variation(product, "color", "Red")
        _variation(product, "size", "S", variant_id="1", title="Black / S")
        _variation(product, "size", "M", variant_id="3", title="White / M")
        _image(product, "1", sort_order=0)
        _image(product, "3", sort_order=1)
        _image(product, "9", src="https://img.example/mock/x1.jpg", sort_order=2)
        _image(product, "9", src="https://img.example/mock/x2.jpg", sort_order=3)
        # Red unresolved: two unknown-group images but TWO would-be candidates is fine
        # for elimination only when a single colour remains — here it applies (only Red left).
        rebuild_color_image_map(product)
        red = ProductColorImage.objects.get(product=product, color_value="red")
        self.assertEqual(red.source, ProductColorImage.SOURCE_HEURISTIC)
        self.assertEqual(len(red.image_id_list()), 2)

    def test_truly_unresolved_color_row_is_empty(self):
        product = _product("Void Tee")
        _variation(product, "color", "Black")
        _variation(product, "color", "Red")
        _variation(product, "color", "Green")
        _variation(product, "size", "S", variant_id="1", title="Black / S")
        _image(product, "1", sort_order=0)
        _image(product, "8", sort_order=1)  # unknown group, 2 candidate colours -> ambiguous
        rebuild_color_image_map(product)
        red = ProductColorImage.objects.get(product=product, color_value="red")
        green = ProductColorImage.objects.get(product=product, color_value="green")
        self.assertEqual(red.image_id_list(), [])
        self.assertEqual(green.image_id_list(), [])


class ReviewRegressionTests(TestCase):
    """Regressions pinned after the adversarial review of this phase."""

    def test_manual_row_with_mixed_case_survives_rebuild(self):
        """A manual pin saved as 'Black' must be recognized (and normalized), not
        shadowed by a fresh 'black' row and deleted by the cleanup."""
        product = _product("Case Tee")
        _variation(product, "color", "Black", variant_id="1")
        img = _image(product, "1,2")
        row = ProductColorImage(product=product, color_value="Black", image_ids="777",
                                source=ProductColorImage.SOURCE_MANUAL, confidence=1.0)
        row.save()
        self.assertEqual(row.color_value, "black")   # normalized on save
        # simulate a legacy non-normalized row written before the save() hook
        ProductColorImage.objects.filter(pk=row.pk).update(color_value="Black")
        rebuild_color_image_map(product)
        rows = ProductColorImage.objects.filter(product=product)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows[0].source, ProductColorImage.SOURCE_MANUAL)
        self.assertEqual(rows[0].image_ids, "777")

    def test_shared_image_only_joins_its_matched_colors(self):
        """An image carrying Black+White variant ids must NOT appear in Red's list."""
        product = _product("Scope Tee")
        _variation(product, "color", "Black")
        _variation(product, "color", "White")
        _variation(product, "color", "Red")
        img_b = _image(product, "1", sort_order=0)
        img_w = _image(product, "3", sort_order=1)
        img_bw = _image(product, "1,3", sort_order=2)
        img_r = _image(product, "5", sort_order=3)
        payload = {
            "options": [{"type": "color", "values": [
                {"id": 10, "title": "Black"}, {"id": 11, "title": "White"},
                {"id": 12, "title": "Red"}]}],
            "variants": [{"id": 1, "options": [10]}, {"id": 3, "options": [11]},
                         {"id": 5, "options": [12]}],
        }
        rebuild_color_image_map(product, payload=payload)
        red = ProductColorImage.objects.get(product=product, color_value="red")
        black = ProductColorImage.objects.get(product=product, color_value="black")
        self.assertEqual(red.image_id_list(), [img_r.id])
        self.assertEqual(black.image_id_list(), [img_b.id, img_bw.id])
        self.assertNotIn(img_bw.id, red.image_id_list())
        self.assertNotIn(img_w.id, black.image_id_list())

    def test_payload_drift_falls_back_to_color_row_ids(self):
        """After variant-id drift the payload ids no longer intersect the frozen
        gallery ids — the colour-row ids (also frozen at first sync) must still
        resolve the mapping instead of blanking previously-correct rows."""
        product = _product("Drift Tee")
        _variation(product, "color", "Black", variant_id="1")
        _variation(product, "color", "White", variant_id="3")
        img_b = _image(product, "1,2", sort_order=0)
        img_w = _image(product, "3,4", sort_order=1)
        drifted_payload = {
            "options": [{"type": "color", "values": [
                {"id": 10, "title": "Black"}, {"id": 11, "title": "White"}]}],
            "variants": [{"id": 901, "options": [10]}, {"id": 903, "options": [11]}],
        }
        rebuild_color_image_map(product, payload=drifted_payload)
        black = ProductColorImage.objects.get(product=product, color_value="black")
        white = ProductColorImage.objects.get(product=product, color_value="white")
        self.assertEqual(black.image_id_list(), [img_b.id])
        self.assertEqual(white.image_id_list(), [img_w.id])

    def test_title_vote_abort_includes_resolved_colors(self):
        """Scrambled-title evidence involving an already-RESOLVED colour must still
        abort the VOTE (the filter-then-scan hole found in review). The image may
        then be assigned by elimination — a title-independent heuristic — but never
        with 'variant-title vote' provenance."""
        product = _product("Abort Tee")
        _variation(product, "color", "Black", variant_id="1")   # resolved via colour row
        _variation(product, "color", "White")
        _variation(product, "size", "L", variant_id="5", title="Black / L")
        _variation(product, "size", "M", variant_id="6", title="White / M")
        _image(product, "1", sort_order=0)
        # unassigned image voted by BOTH colours' titles -> provably scrambled
        img_unknown = _image(product, "5,6", sort_order=1)
        rebuild_color_image_map(product)
        white = ProductColorImage.objects.get(product=product, color_value="white")
        self.assertNotIn("title", white.detail)             # the vote did NOT decide
        self.assertIn("elimination", white.detail)
        self.assertEqual(white.image_id_list(), [img_unknown.id])

    def test_title_vote_abort_leaves_rows_empty_when_two_colors_remain(self):
        """Same scrambling but with TWO unresolved colours: elimination cannot fire
        either, so nothing is guessed at all."""
        product = _product("Abort Tee 2")
        _variation(product, "color", "Black", variant_id="1")
        _variation(product, "color", "White")
        _variation(product, "color", "Red")
        _variation(product, "size", "L", variant_id="5", title="Black / L")
        _variation(product, "size", "M", variant_id="6", title="White / M")
        _image(product, "1", sort_order=0)
        _image(product, "5,6", sort_order=1)
        rebuild_color_image_map(product)
        for c in ("white", "red"):
            row = ProductColorImage.objects.get(product=product, color_value=c)
            self.assertEqual(row.image_ids, "", c)

    def test_filename_with_two_unrelated_colors_stays_ambiguous(self):
        product = _product("Ambig Tee")
        _variation(product, "color", "Kelly Green")
        _variation(product, "color", "Green")
        _variation(product, "color", "Navy")
        _image(product, src="https://img.example/kelly-green-vs-navy-front.jpg")
        rebuild_color_image_map(product)
        for c in ("kelly green", "green", "navy"):
            row = ProductColorImage.objects.get(product=product, color_value=c)
            self.assertEqual(row.image_ids, "", c)


class PrecedenceTests(TestCase):
    def setUp(self):
        self.product = _product("Prec Tee")
        _variation(self.product, "color", "Black")
        self.img = _image(self.product, "1,2", sort_order=0)

    def test_manual_row_never_overwritten(self):
        ProductColorImage.objects.create(
            product=self.product, color_value="black", image_ids="999",
            source=ProductColorImage.SOURCE_MANUAL, confidence=1.0)
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_MANUAL)
        self.assertEqual(row.image_ids, "999")

    def test_openai_row_kept_when_new_result_is_weaker(self):
        ProductColorImage.objects.create(
            product=self.product, color_value="black", image_ids=str(self.img.id),
            source=ProductColorImage.SOURCE_OPENAI, confidence=0.6)
        # no payload, no titles -> recompute would be heuristic (single colour)
        rebuild_color_image_map(self.product)
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_OPENAI)

    def test_openai_row_upgraded_by_deterministic(self):
        ProductColorImage.objects.create(
            product=self.product, color_value="black", image_ids="999",
            source=ProductColorImage.SOURCE_OPENAI, confidence=0.6)
        rebuild_color_image_map(self.product, payload=PAYLOAD)
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        self.assertEqual(row.source, ProductColorImage.SOURCE_DETERMINISTIC)
        self.assertEqual(row.image_id_list(), [self.img.id])


class EdgeCaseTests(TestCase):
    def test_no_colors_deletes_all_rows(self):
        product = _product("No Color Tee")
        _image(product, "1")
        ProductColorImage.objects.create(product=product, color_value="ghost")
        summary = rebuild_color_image_map(product)
        self.assertEqual(ProductColorImage.objects.filter(product=product).count(), 0)
        self.assertEqual(summary["colors"], 0)

    def test_no_images_keeps_empty_rows(self):
        product = _product("No Image Tee")
        _variation(product, "color", "Black")
        summary = rebuild_color_image_map(product)
        row = ProductColorImage.objects.get(product=product, color_value="black")
        self.assertEqual(row.image_id_list(), [])
        self.assertEqual(summary["resolved"], 0)

    def test_summary_counts(self):
        product = _product("Sum Tee")
        _variation(product, "color", "Black")
        _variation(product, "color", "White")
        _image(product, "1,2", sort_order=0)
        _image(product, "3,4", sort_order=1)
        summary = rebuild_color_image_map(product, payload=PAYLOAD)
        self.assertEqual(summary["colors"], 2)
        self.assertEqual(summary["resolved"], 2)
        self.assertEqual(summary["sources"].get("deterministic"), 2)
