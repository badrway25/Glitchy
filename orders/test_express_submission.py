"""Printify order submission carries the chosen delivery method.

Before this phase `shipping_method` was absent from the payload entirely, so
Printify defaulted every order to standard even when the customer paid for
something faster. Express additionally uses a different endpoint that may split
a mixed cart into two Printify orders.

Every test here is offline: the client is mocked, no order is ever created.
"""
from unittest import mock

from django.test import TestCase, override_settings

from category.models import Category
from orders.models import Order, OrderProduct
from orders.printify_payload import build_printify_payload
from orders.services import push_order_to_printify
from store.models import Product, Variation


def _order(method="standard", phone="+15550100", email="buyer@example.com"):
    return Order.objects.create(
        first_name="A", last_name="B", phone=phone, email=email,
        address_line_1="1 Main St", city="Austin", state="TX", country="US",
        postal_code="78701", order_total=30, tax=0, ip="1.1.1.1",
        order_number="EXP-1", shipping_method=method, currency="USD")


def _order_product(order):
    cat, _ = Category.objects.get_or_create(category_name="T", slug="t")
    product = Product.objects.create(
        product_name="Exp Tee", slug="exp-tee", price=25, stock=5, category=cat,
        printify_product_id="pp_1", printify_express_eligible=True)
    variation = Variation.objects.create(
        product=product, variation_category="color", variation_value="Black",
        printify_variant_id="12359")
    op = OrderProduct.objects.create(order=order, product=product, quantity=1,
                                     product_price=25, ordered=True)
    op.variations.add(variation)
    return op


class PayloadMethodTests(TestCase):
    def test_standard_maps_to_method_1(self):
        order = _order("standard")
        payload = build_printify_payload(order=order, order_products=[_order_product(order)])
        self.assertEqual(payload["shipping_method"], 1)
        self.assertNotIn("is_printify_express", payload)

    def test_priority_maps_to_method_2(self):
        order = _order("priority")
        payload = build_printify_payload(order=order, order_products=[_order_product(order)])
        self.assertEqual(payload["shipping_method"], 2)

    def test_express_maps_to_method_3_and_flags(self):
        order = _order("printify_express")
        payload = build_printify_payload(order=order, order_products=[_order_product(order)])
        self.assertEqual(payload["shipping_method"], 3)
        self.assertTrue(payload["is_printify_express"])
        # the express endpoint requires both contact fields
        self.assertTrue(payload["address_to"]["email"])
        self.assertTrue(payload["address_to"]["phone"])

    def test_express_without_phone_refuses_to_build(self):
        order = _order("printify_express", phone="")
        with self.assertRaises(ValueError) as ctx:
            build_printify_payload(order=order, order_products=[_order_product(order)])
        self.assertIn("phone", str(ctx.exception))

    def test_express_without_email_refuses_to_build(self):
        order = _order("printify_express", email="")
        with self.assertRaises(ValueError):
            build_printify_payload(order=order, order_products=[_order_product(order)])


@override_settings(PRINTIFY_PUSH_ENABLED=True)
class SubmissionRoutingTests(TestCase):
    def _client(self, express_response=None, standard_response=None):
        client = mock.Mock()
        client.create_express_order.return_value = express_response or {}
        client.create_order.return_value = standard_response or {"id": "std1", "status": "created"}
        return client

    def test_standard_order_uses_normal_endpoint(self):
        order = _order("standard")
        _order_product(order)
        client = self._client()
        with mock.patch("orders.printify.get_client", return_value=client), \
             mock.patch("printify_integration.printify_client.get_client", return_value=client):
            push_order_to_printify(order, auto_send=False)
        client.create_order.assert_called_once()
        client.create_express_order.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.printify_order_id, "std1")

    def test_express_order_uses_express_endpoint(self):
        order = _order("printify_express")
        _order_product(order)
        client = self._client(express_response={"data": [
            {"id": "exp1", "attributes": {"fulfilment_type": "express"}}]})
        with mock.patch("printify_integration.printify_client.get_client", return_value=client):
            push_order_to_printify(order, auto_send=False)
        client.create_express_order.assert_called_once()
        client.create_order.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.printify_order_id, "exp1")

    def test_split_response_records_sibling_order(self):
        """A mixed Express cart comes back as TWO Printify orders — we adopt the
        express one and keep a safe breadcrumb for the ordinary sibling."""
        order = _order("printify_express")
        _order_product(order)
        client = self._client(express_response={"data": [
            {"id": "ord2", "attributes": {"fulfilment_type": "ordinary"}},
            {"id": "exp1", "attributes": {"fulfilment_type": "express"}}]})
        with mock.patch("printify_integration.printify_client.get_client", return_value=client):
            push_order_to_printify(order, auto_send=False)
        order.refresh_from_db()
        self.assertEqual(order.printify_order_id, "exp1")
        self.assertIn("ord2", order.printify_last_error)
        self.assertIn("split", order.printify_last_error.lower())

    def test_push_disabled_makes_no_call_at_all(self):
        order = _order("printify_express")
        _order_product(order)
        client = self._client()
        with override_settings(PRINTIFY_PUSH_ENABLED=False), \
             mock.patch("printify_integration.printify_client.get_client", return_value=client):
            self.assertIsNone(push_order_to_printify(order, auto_send=False))
        client.create_express_order.assert_not_called()
        client.create_order.assert_not_called()
