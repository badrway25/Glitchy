"""Tests for the variant thumbnail resolver (store/variant_thumbnail.py).

One backend-side authority decides which image a cart/order line shows:
snapshot on the line → ProductColorImage for the selected colour → product
main image → first gallery image → '' (template renders the placeholder).
"""
from django.test import TestCase

from category.models import Category
from store.models import Product, ProductColorImage, ProductImage, Variation

from store.variant_thumbnail import (normalize_color, product_fallback_image_url,
                                     resolve_variant_image)


def _product(name="Thumb Tee"):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    return Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                                  price=20, stock=5, category=cat)


def _image(product, src, sort_order=0):
    return ProductImage.objects.create(product=product, printify_src=src,
                                       sort_order=sort_order)


def _map_row(product, color, images, primary=None, source="deterministic"):
    return ProductColorImage.objects.create(
        product=product, color_value=color,
        image_ids=",".join(str(i.id) for i in images),
        primary_image=primary or (images[0] if images else None), source=source)


class NormalizeColorTests(TestCase):
    def test_english_passthrough(self):
        self.assertEqual(normalize_color(" Black "), "black")

    def test_italian_and_french_synonyms(self):
        for raw, expected in [("Nero", "black"), ("noir", "black"),
                              ("Bianco", "white"), ("BLANC", "white"),
                              ("Blu", "blue"), ("bleu", "blue")]:
            self.assertEqual(normalize_color(raw), expected, raw)

    def test_unknown_color_lowercased(self):
        self.assertEqual(normalize_color("Dark Heather"), "dark heather")

    def test_empty_safe(self):
        self.assertEqual(normalize_color(None), "")
        self.assertEqual(normalize_color("  "), "")


class ResolveVariantImageTests(TestCase):
    def setUp(self):
        self.product = _product()
        self.img_black = _image(self.product, "https://img.example/b.jpg", 0)
        self.img_white = _image(self.product, "https://img.example/w.jpg", 1)
        _map_row(self.product, "black", [self.img_black])
        _map_row(self.product, "white", [self.img_white])

    def test_black_resolves_black_image(self):
        img = resolve_variant_image(self.product, {"color": "Black"})
        self.assertEqual(img.id, self.img_black.id)

    def test_white_resolves_white_image(self):
        img = resolve_variant_image(self.product, {"color": "White"})
        self.assertEqual(img.id, self.img_white.id)

    def test_synonyms_reach_the_mapping(self):
        for raw in ("Nero", "noir"):
            img = resolve_variant_image(self.product, {"color": raw})
            self.assertEqual(img.id, self.img_black.id, raw)

    def test_raw_value_wins_over_synonym_normalization(self):
        """Review regression: mapping rows store the RAW lowercased variation value.
        A 'Blu' variation with a 'blu' mapping row must resolve — the normalized
        'blue' key alone would miss it."""
        img_blu = _image(self.product, "https://img.example/blu.jpg", 2)
        _map_row(self.product, "blu", [img_blu])
        img = resolve_variant_image(self.product, {"color": "Blu"})
        self.assertEqual(img.id, img_blu.id)
        # and a French 'Rose' pick still reaches an English 'pink' row
        img_pink = _image(self.product, "https://img.example/pink.jpg", 3)
        _map_row(self.product, "pink", [img_pink])
        img = resolve_variant_image(self.product, {"color": "Rose"})
        self.assertEqual(img.id, img_pink.id)

    def test_variation_objects_accepted(self):
        color = Variation.objects.create(product=self.product, variation_category="color",
                                         variation_value="White")
        size = Variation.objects.create(product=self.product, variation_category="size",
                                        variation_value="L")
        img = resolve_variant_image(self.product, variations=[size, color])
        self.assertEqual(img.id, self.img_white.id)

    def test_row_without_primary_uses_first_listed_image(self):
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        row.primary_image = None
        row.save()
        img = resolve_variant_image(self.product, {"color": "Black"})
        self.assertEqual(img.id, self.img_black.id)

    def test_unresolved_row_returns_none(self):
        ProductColorImage.objects.create(product=self.product, color_value="red",
                                         image_ids="")
        self.assertIsNone(resolve_variant_image(self.product, {"color": "Red"}))

    def test_unknown_color_returns_none(self):
        self.assertIsNone(resolve_variant_image(self.product, {"color": "Chartreuse"}))

    def test_no_color_returns_none(self):
        self.assertIsNone(resolve_variant_image(self.product, {"size": "L"}))
        self.assertIsNone(resolve_variant_image(self.product, {}))
        self.assertIsNone(resolve_variant_image(self.product, None))

    def test_stale_image_id_skipped(self):
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        row.image_ids = f"99999,{self.img_black.id}"
        row.primary_image = None
        row.save()
        img = resolve_variant_image(self.product, {"color": "Black"})
        self.assertEqual(img.id, self.img_black.id)

    def test_primary_of_other_product_rejected(self):
        other = _product("Other Tee")
        foreign = _image(other, "https://img.example/foreign.jpg")
        row = ProductColorImage.objects.get(product=self.product, color_value="black")
        row.primary_image = foreign          # corrupted/poisoned row
        row.image_ids = str(foreign.id)
        row.save()
        self.assertIsNone(resolve_variant_image(self.product, {"color": "Black"}))


class FallbackUrlTests(TestCase):
    def test_gallery_display_url_when_no_main_image(self):
        p = _product("NoMain Tee")
        _image(p, "https://img.example/g1.jpg", 0)
        self.assertEqual(product_fallback_image_url(p), "https://img.example/g1.jpg")

    def test_empty_when_nothing(self):
        p = _product("Bare Tee")
        self.assertEqual(product_fallback_image_url(p), "")


class CartLineResolutionTests(TestCase):
    """CartItem.line_image_url(): snapshot first, mapping second, fallback third."""

    def setUp(self):
        from carts.models import Cart, CartItem
        self.product = _product("Line Tee")
        self.img_black = _image(self.product, "https://img.example/b.jpg", 0)
        self.img_white = _image(self.product, "https://img.example/w.jpg", 1)
        _map_row(self.product, "black", [self.img_black])
        self.color_black = Variation.objects.create(
            product=self.product, variation_category="color", variation_value="Black")
        self.cart = Cart.objects.create(cart_id="test-session")
        self.item = CartItem.objects.create(product=self.product, cart=self.cart,
                                            quantity=1, is_active=True)
        self.item.variations.add(self.color_black)

    def test_snapshot_wins(self):
        self.item.selected_image = self.img_white
        self.item.save()
        self.assertEqual(self.item.line_image_url(), "https://img.example/w.jpg")

    def test_snapshot_of_other_product_ignored(self):
        other = _product("Foreign Tee")
        foreign = _image(other, "https://img.example/foreign.jpg")
        self.item.selected_image = foreign
        self.item.save()
        # falls through to the colour mapping
        self.assertEqual(self.item.line_image_url(), "https://img.example/b.jpg")

    def test_mapping_used_without_snapshot(self):
        self.assertEqual(self.item.line_image_url(), "https://img.example/b.jpg")

    def test_fallback_without_variations(self):
        self.item.variations.clear()
        self.assertEqual(self.item.line_image_url(), "https://img.example/b.jpg")
        # (product fallback = first gallery image here: no main image file)

    def test_color_label(self):
        self.assertEqual(self.item.line_color_value(), "Black")
        self.item.variations.clear()
        self.assertEqual(self.item.line_color_value(), "")


class OrderLineResolutionTests(TestCase):
    def setUp(self):
        from orders.models import Order, OrderProduct
        self.product = _product("Order Tee")
        self.img_black = _image(self.product, "https://img.example/b.jpg", 0)
        _map_row(self.product, "black", [self.img_black])
        self.color = Variation.objects.create(
            product=self.product, variation_category="color", variation_value="Black")
        order = Order.objects.create(order_number="T-1", email="t@x.com",
                                     order_total=20, tax=0, status="New", ip="1.1.1.1")
        self.op = OrderProduct.objects.create(
            order=order, product=self.product, quantity=1, product_price=20,
            ordered=True)
        self.op.variations.add(self.color)

    def test_snapshot_first_then_mapping(self):
        self.assertEqual(self.op.line_image_url(), "https://img.example/b.jpg")
        white = _image(self.product, "https://img.example/w.jpg", 1)
        self.op.selected_image = white
        self.op.save()
        self.assertEqual(self.op.line_image_url(), "https://img.example/w.jpg")

    def test_snapshot_survives_mapping_deletion(self):
        self.op.selected_image = self.img_black
        self.op.save()
        ProductColorImage.objects.all().delete()
        self.assertEqual(self.op.line_image_url(), "https://img.example/b.jpg")
