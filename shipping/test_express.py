"""Printify Express eligibility rules (shipping/express.py).

Express is never global: it is offered only when the destination, the address
and every relevant product/variant allow it, AND Printify actually returned a
`printify_express` price for that cart. The rules encoded here come from
Printify's official documentation (US mainland only, no AK/HI, no PO Box,
eligible products/variants only, phone + email required at order time).
"""
from django.test import SimpleTestCase, TestCase, override_settings

from category.models import Category
from shipping.express import (EXPRESS_METHOD, destination_allows_express,
                              express_blockers, is_po_box, normalize_state)
from store.models import Product, Variation


class PoBoxDetectionTests(SimpleTestCase):
    def test_detects_common_po_box_spellings(self):
        for line in ("PO Box 123", "p.o. box 9", "POST OFFICE BOX 4",
                     "PO-BOX 22", "Postbus 12", "po box", "P O Box 17"):
            self.assertTrue(is_po_box(line), line)

    def test_normal_addresses_are_not_po_boxes(self):
        for line in ("123 Main Street", "Boxwood Avenue 4", "Via Roma 1",
                     "12 Post Road", "", None, "Boxer Street 9"):
            self.assertFalse(is_po_box(line), line)


class StateNormalizationTests(SimpleTestCase):
    def test_names_and_codes(self):
        for raw, expected in [("AK", "AK"), ("alaska", "AK"), (" Hawaii ", "HI"),
                              ("HI", "HI"), ("California", "CA"), ("ny", "NY")]:
            self.assertEqual(normalize_state(raw), expected, raw)

    def test_unknown_state_passes_through_uppercased(self):
        self.assertEqual(normalize_state("Lombardia"), "LOMBARDIA")
        self.assertEqual(normalize_state(None), "")


class DestinationRulesTests(SimpleTestCase):
    def test_us_mainland_allowed(self):
        ok, reason = destination_allows_express("US", state="CA", address1="1 Main St")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_alaska_and_hawaii_blocked(self):
        for state in ("AK", "Alaska", "HI", "hawaii"):
            ok, reason = destination_allows_express("US", state=state, address1="1 Main St")
            self.assertFalse(ok, state)
            self.assertEqual(reason, "destination_not_supported")

    def test_po_box_blocked(self):
        ok, reason = destination_allows_express("US", state="CA", address1="PO Box 88")
        self.assertFalse(ok)
        self.assertEqual(reason, "po_box")

    def test_po_box_checked_on_second_line_too(self):
        ok, reason = destination_allows_express("US", state="CA", address1="1 Main St",
                                                address2="P.O. Box 5")
        self.assertFalse(ok)
        self.assertEqual(reason, "po_box")

    def test_non_us_blocked(self):
        for country in ("BE", "IT", "FR", "CA", "GB", ""):
            ok, reason = destination_allows_express(country, state="", address1="Via Roma 1")
            self.assertFalse(ok, country)
            self.assertEqual(reason, "destination_not_supported")


class CartEligibilityTests(TestCase):
    def setUp(self):
        cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
        self.eligible = Product.objects.create(
            product_name="Express Tee", slug="express-tee", price=25, stock=5,
            category=cat, printify_express_eligible=True)
        self.plain = Product.objects.create(
            product_name="Plain Tee", slug="plain-tee", price=25, stock=5,
            category=cat, printify_express_eligible=False)

    def _item(self, product, qty=1):
        class _Item:
            def __init__(self, p, q):
                self.product = p
                self.quantity = q
        return _Item(product, qty)

    def test_all_eligible_no_blockers(self):
        blockers = express_blockers([self._item(self.eligible)], country="US",
                                    state="CA", address1="1 Main St", phone="+15550100")
        self.assertEqual(blockers, [])

    def test_missing_phone_blocks(self):
        blockers = express_blockers([self._item(self.eligible)], country="US",
                                    state="CA", address1="1 Main St", phone="")
        self.assertIn("phone_required", blockers)

    def test_ineligible_product_blocks(self):
        blockers = express_blockers([self._item(self.plain)], country="US",
                                    state="CA", address1="1 Main St", phone="+15550100")
        self.assertIn("items_not_eligible", blockers)

    def test_mixed_cart_reports_partial(self):
        blockers = express_blockers(
            [self._item(self.eligible), self._item(self.plain)], country="US",
            state="CA", address1="1 Main St", phone="+15550100")
        self.assertIn("items_not_eligible", blockers)

    def test_destination_and_phone_blockers_combine(self):
        blockers = express_blockers([self._item(self.eligible)], country="BE",
                                    state="", address1="Rue 1", phone="")
        self.assertIn("destination_not_supported", blockers)
        self.assertIn("phone_required", blockers)

    def test_variant_level_eligibility_respected(self):
        """A product flagged eligible but whose CHOSEN variant is not eligible
        must not qualify (Printify eligibility is per variant)."""
        colour = Variation.objects.create(
            product=self.eligible, variation_category="color",
            variation_value="Neon", printify_express_eligible=False)

        class _Item:
            def __init__(self, p, v):
                self.product = p
                self.quantity = 1
                self._v = v

            @property
            def variations(self):
                class _QS:
                    def __init__(self, rows):
                        self._rows = rows

                    def all(self):
                        return self._rows
                return _QS([self._v])

        blockers = express_blockers([_Item(self.eligible, colour)], country="US",
                                    state="CA", address1="1 Main St", phone="+15550100")
        self.assertIn("items_not_eligible", blockers)


@override_settings(SHIPPING_EXPRESS_ENABLED=False)
class KillSwitchTests(TestCase):
    def test_disabled_setting_blocks_everything(self):
        cat, _ = Category.objects.get_or_create(category_name="T", slug="t")
        p = Product.objects.create(product_name="X", slug="x", price=10, stock=1,
                                   category=cat, printify_express_eligible=True)

        class _Item:
            product = p
            quantity = 1

        blockers = express_blockers([_Item()], country="US", state="CA",
                                    address1="1 Main St", phone="+15550100")
        self.assertIn("express_disabled", blockers)


class ConstantsTests(SimpleTestCase):
    def test_method_name_matches_printify_cost_map_key(self):
        # POST /orders/shipping.json returns {"printify_express": 799, ...}
        self.assertEqual(EXPRESS_METHOD, "printify_express")
