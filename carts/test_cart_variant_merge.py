"""Regression: re-adding an identical variant must bump quantity, not fork a row.

Found in live QA (2026-08-15): adding the same product+colour+size twice created
two separate qty-1 cart lines. Root cause — add_cart compared the requested
variation list (POST-field order) against `item.variations.all()` (DB/PK order,
Variation has no Meta.ordering); when the orders differed the ordered-list `in`
test never matched, so every re-add of a multi-variation product spawned a new
line. The fix compares variation *sets*. These tests pin both branches.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from carts.models import CartItem
from category.models import Category
from store.models import Product, Variation


def _make_product():
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    p = Product.objects.create(product_name="Merge Tee", slug="merge-tee",
                               price=25, stock=10, category=cat, is_available=True)
    for value in ("Black", "White"):
        Variation.objects.create(product=p, variation_category="color",
                                 variation_value=value, is_active=True)
    for value in ("XS", "M"):
        Variation.objects.create(product=p, variation_category="size",
                                 variation_value=value, is_active=True)
    return p


class GuestCartMergeTests(TestCase):
    def setUp(self):
        self.product = _make_product()
        self.url = reverse("add_cart", args=[self.product.id])

    def _add(self, fields):
        return self.client.post(self.url, fields,
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_identical_variant_merges_into_one_line(self):
        self._add({"color": "Black", "size": "XS"})
        self._add({"color": "Black", "size": "XS"})
        lines = CartItem.objects.filter(product=self.product)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().quantity, 2)

    def test_merges_even_when_post_field_order_differs(self):
        # This is the exact trigger: same variant, different field order.
        self._add({"color": "Black", "size": "XS"})
        self._add({"size": "XS", "color": "Black"})
        lines = CartItem.objects.filter(product=self.product)
        self.assertEqual(lines.count(), 1, "same variant must not fork on field order")
        self.assertEqual(lines.first().quantity, 2)

    def test_different_size_stays_separate(self):
        self._add({"color": "Black", "size": "XS"})
        self._add({"color": "Black", "size": "M"})
        self.assertEqual(CartItem.objects.filter(product=self.product).count(), 2)

    def test_different_colour_stays_separate(self):
        self._add({"color": "Black", "size": "XS"})
        self._add({"color": "White", "size": "XS"})
        self.assertEqual(CartItem.objects.filter(product=self.product).count(), 2)


class AuthCartMergeTests(TestCase):
    """The live repro was an authenticated shopper — cover that branch too."""

    def setUp(self):
        self.product = _make_product()
        self.url = reverse("add_cart", args=[self.product.id])
        self.user = Account.objects.create_user(
            first_name="Qa", last_name="Tester", username="qamerge",
            email="qa-merge@example.com", password="x")
        # create_user leaves is_active=False on this model; an inactive user is
        # treated as anonymous by ModelBackend and would fall into the guest branch.
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.client.force_login(self.user)

    def _add(self, fields):
        return self.client.post(self.url, fields,
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_identical_variant_merges_for_logged_in_user(self):
        self._add({"color": "Black", "size": "XS"})
        self._add({"size": "XS", "color": "Black"})
        lines = CartItem.objects.filter(product=self.product, user=self.user)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().quantity, 2)
