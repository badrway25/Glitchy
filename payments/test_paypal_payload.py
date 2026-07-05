"""PayPal payload integrity tests — everything mocked, sandbox-only semantics.

No real PayPal call, no capture, no live keys.
"""
import json
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core import signing
from django.test import Client, TestCase, override_settings

from payments.paypal_payload import PayloadMismatch, build_order_payload


def _order(**kw):
    base = dict(order_number="O-77", first_name="Marco", last_name="Rossi",
                email="m@example.com", phone="+393331234567",
                address_line_1="Via Roma 12", address_line_2="Int. 3",
                city="Milano", state="MI", postal_code="20100", country="IT",
                shipping_cost=6.90, tax=0.52, discount=0.0, order_total=33.42)
    base.update(kw)
    return SimpleNamespace(**base)


def _items():
    return [SimpleNamespace(product=SimpleNamespace(product_name="Tee Uno", price=13.0), quantity=2)]
    # item_total = 26.00; +6.90 ship +0.52 tax = 33.42 (grand)


class PayloadBuilderTests(TestCase):
    def test_amount_equals_cart_total_with_exact_breakdown(self):
        p = build_order_payload(_order(), _items(), currency="EUR")
        pu = p["purchase_units"][0]
        self.assertEqual(pu["amount"]["value"], "33.42")
        self.assertEqual(pu["amount"]["currency_code"], "EUR")
        b = pu["amount"]["breakdown"]
        self.assertEqual(b["item_total"]["value"], "26.00")
        self.assertEqual(b["shipping"]["value"], "6.90")
        self.assertEqual(b["tax_total"]["value"], "0.52")
        self.assertEqual(b["discount"]["value"], "0.00")
        # identity holds in Decimal, no float residue anywhere
        total = (Decimal(b["item_total"]["value"]) + Decimal(b["shipping"]["value"])
                 + Decimal(b["tax_total"]["value"]) - Decimal(b["discount"]["value"]))
        self.assertEqual(str(total), pu["amount"]["value"])

    def test_items_are_real_products(self):
        p = build_order_payload(_order(), _items())
        it = p["purchase_units"][0]["items"][0]
        self.assertEqual(it["name"], "Tee Uno")
        self.assertEqual(it["unit_amount"]["value"], "13.00")
        self.assertEqual(it["quantity"], "2")
        self.assertEqual(it["category"], "PHYSICAL_GOODS")

    def test_coupon_discount_derived_and_balancing(self):
        # coupon applied: grand 30.42 instead of 33.42 -> derived discount 3.00
        p = build_order_payload(_order(order_total=30.42), _items())
        b = p["purchase_units"][0]["amount"]["breakdown"]
        self.assertEqual(b["discount"]["value"], "3.00")
        self.assertEqual(p["purchase_units"][0]["amount"]["value"], "30.42")

    def test_shipping_address_is_checkout_address(self):
        sh = build_order_payload(_order(), _items())["purchase_units"][0]["shipping"]
        self.assertEqual(sh["name"]["full_name"], "Marco Rossi")
        a = sh["address"]
        self.assertEqual(a["address_line_1"], "Via Roma 12")
        self.assertEqual(a["admin_area_2"], "Milano")
        self.assertEqual(a["admin_area_1"], "MI")
        self.assertEqual(a["postal_code"], "20100")
        self.assertEqual(a["country_code"], "IT")

    def test_shipping_preference_is_set_provided_address(self):
        p = build_order_payload(_order(), _items())
        ctx = p["application_context"]
        self.assertEqual(ctx["shipping_preference"], "SET_PROVIDED_ADDRESS")
        self.assertEqual(ctx["user_action"], "PAY_NOW")

    def test_valid_e164_phone_included(self):
        sh = build_order_payload(_order(), _items())["purchase_units"][0]["shipping"]
        self.assertEqual(sh["phone_number"]["country_code"], "39")
        self.assertEqual(sh["phone_number"]["national_number"], "3331234567")

    def test_invalid_phone_omitted_without_breaking(self):
        sh = build_order_payload(_order(phone="12"), _items())["purchase_units"][0]["shipping"]
        self.assertNotIn("phone_number", sh)

    def test_mismatch_refused(self):
        with self.assertRaises(PayloadMismatch):
            build_order_payload(_order(order_total=99.99), _items())  # above components
        with self.assertRaises(PayloadMismatch):
            build_order_payload(_order(order_total=0), [])            # non-positive


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PayPalCreateOrderEndpointTests(TestCase):
    def _setup_order(self, **order_kw):
        from category.models import Category
        from store.models import Product
        from carts.models import Cart, CartItem
        from orders.models import Order
        cat, _ = Category.objects.get_or_create(category_name="Tees", slug="tees")
        p, _ = Product.objects.get_or_create(
            product_name="Tee Uno", slug="tee-uno", category=cat,
            defaults={"price": 13.0, "stock": 10, "is_available": True, "description": "t"})
        c = Client()
        c.get("/")
        cart, _x = Cart.objects.get_or_create(cart_id=c.session.session_key)
        CartItem.objects.create(product=p, cart=cart, quantity=2)
        base = dict(order_number="O-88", first_name="Marco", last_name="Rossi",
                    email="m@example.com", phone="+393331234567",
                    address_line_1="Via Roma 12", country="IT", state="MI", city="Milano",
                    postal_code="20100", shipping_cost=6.90, tax=0.52,
                    order_total=33.42, ip="127.0.0.1", is_ordered=False, status="New",
                    is_guest=True, session_key=c.session.session_key)
        base.update(order_kw)
        Order.objects.create(**base)
        return c

    def _post(self, c, order_number="O-88"):
        return c.post("/orders/paypal/create-order/", json.dumps({"order_number": order_number}),
                      content_type="application/json")

    def test_success_returns_paypal_id_and_sends_full_payload(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = MagicMock(status_code=201, json=lambda: {"id": "PP-123"})
            r = self._post(c)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "PP-123")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["purchase_units"][0]["amount"]["value"], "33.42")
        self.assertEqual(payload["purchase_units"][0]["shipping"]["address"]["admin_area_2"], "Milano")
        self.assertEqual(
            payload["application_context"]["shipping_preference"],
            "SET_PROVIDED_ADDRESS")
        self.assertNotIn("tok", str(r.content))               # token never surfaces

    def test_missing_address_blocks_before_paypal(self):
        c = self._setup_order(address_line_1="")
        with patch("requests.post") as post:
            r = self._post(c)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(post.called)
        self.assertIn("delivery address", r.json()["error"])

    def test_mismatch_blocks_with_409(self):
        c = self._setup_order(order_total=99.99)              # impossible vs components
        with patch("requests.post") as post:
            r = self._post(c)
        self.assertEqual(r.status_code, 409)
        self.assertFalse(post.called)
        self.assertIn("safety", r.json()["error"])

    def test_paypal_error_mapped_elegantly(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = MagicMock(status_code=422, json=lambda: {
                "details": [{"issue": "SHIPPING_ADDRESS_INVALID"}]})
            r = self._post(c)
        self.assertEqual(r.status_code, 502)
        self.assertIn("shipping address", r.json()["error"].lower())

    def test_unavailable_maps_to_card_suggestion(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=False):
            r = self._post(c)
        self.assertEqual(r.status_code, 502)
        self.assertIn("card", r.json()["error"].lower())


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PayPalServerCaptureTests(TestCase):
    """Server-side capture endpoint — replaces the hanging client actions.order.capture()."""

    def _setup(self, **kw):
        # reuse the create-order fixture
        t = PayPalCreateOrderEndpointTests()
        t.client = self.client
        return PayPalCreateOrderEndpointTests._setup_order(self, **kw)

    _setup_order = PayPalCreateOrderEndpointTests._setup_order

    def _capture(self, c, pp_id="PP-OID-1"):
        return c.post("/orders/paypal/capture/",
                      json.dumps({"order_number": "O-88", "paypal_order_id": pp_id}),
                      content_type="application/json")

    def _pp_response(self, status="COMPLETED", amount="33.42", currency="EUR"):
        return MagicMock(status_code=201, json=lambda: {
            "status": status,
            "purchase_units": [{"payments": {"captures": [
                {"id": "CAP-777", "amount": {"value": amount, "currency_code": currency}}]}}]})

    def test_capture_success_finalizes_order(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = self._pp_response()
            r = self._capture(c)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["payment_id"], "CAP-777")   # REAL capture id, not order id
        self.assertIn("redirect_url", r.json())
        from orders.models import Order, Payment
        o = Order.objects.get(order_number="O-88")
        self.assertTrue(o.is_ordered)
        self.assertEqual(Payment.objects.get(payment_id="CAP-777").amount_paid, "33.42")
        self.assertNotIn("tok", r.content.decode())

    def test_amount_mismatch_blocks_finalization(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = self._pp_response(amount="1.00")
            r = self._capture(c)
        self.assertEqual(r.status_code, 409)
        from orders.models import Order
        self.assertFalse(Order.objects.get(order_number="O-88").is_ordered)

    def test_instrument_declined_maps_to_retry(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = MagicMock(status_code=422, json=lambda: {
                "details": [{"issue": "INSTRUMENT_DECLINED"}]})
            r = self._capture(c)
        self.assertEqual(r.status_code, 402)
        self.assertTrue(r.json().get("retry"))
        self.assertIn("declined", r.json()["message"].lower())

    def test_pending_status_polite_message(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post") as post:
            post.return_value = self._pp_response(status="PENDING")
            r = self._capture(c)
        self.assertEqual(r.status_code, 200)                 # pending is ok:true now
        self.assertEqual(r.json()["status"], "pending")

    def test_network_failure_is_elegant_502(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True), \
             patch("orders.paypal._access_token", return_value="tok"), \
             patch("requests.post", side_effect=Exception("boom")):
            r = self._capture(c)
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("boom", r.json()["message"])

    def test_missing_or_bad_capture_id_rejected(self):
        c = self._setup_order()
        with patch("orders.paypal.paypal_available", return_value=True):
            r = self._capture(c, pp_id="")
        self.assertEqual(r.status_code, 502)


class PayPalTemplateGuardTests(TestCase):
    """The payments template must keep the single-button, no-client-capture contract."""

    def _tpl(self):
        import pathlib
        from django.conf import settings as dj
        return (pathlib.Path(dj.BASE_DIR) / "templates" / "orders" /
                "payments.html").read_text(encoding="utf-8")

    def test_single_gold_paypal_button(self):
        t = self._tpl()
        self.assertIn("fundingSource: paypal.FUNDING.PAYPAL", t)
        self.assertIn("color: 'gold'", t)
        self.assertIn("disable-funding=paylater,card,credit,venmo", t)
        self.assertNotIn("color: 'black'", t)

    def test_no_client_capture_no_manual_window(self):
        t = self._tpl()
        self.assertNotIn("actions.order.capture", t)          # server capture only
        self.assertNotIn("window.open(", t)                   # SDK owns the popup
        self.assertIn("__ppRendered", t)                      # render-once guard
        self.assertEqual(t.count("paypal-button-container"), 2)  # 1 div + 1 render call

    def test_loading_and_timeout_states_present(self):
        t = self._tpl()
        for marker in ("Connecting to PayPal", "Confirming your payment",
                       "taking longer than expected", "ppStatus", "ppReconcileThenError"):
            self.assertIn(marker, t)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PayPalReconciliationTests(TestCase):
    """Completed-in-DB / frontend-timeout reconciliation — the live bug."""

    _setup_order = PayPalCreateOrderEndpointTests._setup_order

    def _complete(self, c):
        from orders.models import Order, Payment
        o = Order.objects.get(order_number="O-88")
        p = Payment.objects.create(payment_id="CAP-DONE", email=o.email,
                                   payment_method="PayPal", amount_paid="33.42",
                                   status="COMPLETED")
        o.payment = p; o.is_ordered = True; o.save()
        return o

    def test_capture_on_already_completed_order_is_idempotent_success(self):
        c = self._setup_order()
        self._complete(c)
        with patch("requests.post") as post:                 # NO PayPal call may happen
            r = c.post("/orders/paypal/capture/",
                       json.dumps({"order_number": "O-88", "paypal_order_id": "PP-X"}),
                       content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(post.called)                        # no second capture, ever
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["status"], "already_completed")
        self.assertEqual(d["payment_id"], "CAP-DONE")
        self.assertIn("redirect_url", d)

    def test_status_endpoint_finds_completed_payment(self):
        c = self._setup_order()
        self._complete(c)
        r = c.post("/orders/paypal/status/", json.dumps({"order_number": "O-88"}),
                   content_type="application/json")
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["status"], "completed")
        self.assertIn("redirect_url", d)

    def test_status_endpoint_processing_when_not_finalized(self):
        c = self._setup_order()
        r = c.post("/orders/paypal/status/", json.dumps({"order_number": "O-88"}),
                   content_type="application/json")
        self.assertEqual(r.json()["status"], "processing")

    def test_status_endpoint_unknown_for_foreign_order(self):
        c = self._setup_order()
        r = c.post("/orders/paypal/status/", json.dumps({"order_number": "NOPE"}),
                   content_type="application/json")
        self.assertEqual(r.json()["status"], "unknown")

    def test_already_captured_issue_reconciles_from_db(self):
        c = self._setup_order()
        from orders.models import Order, Payment
        o = Order.objects.get(order_number="O-88")
        p = Payment.objects.create(payment_id="CAP-R", email=o.email,
                                   payment_method="PayPal", amount_paid="33.42",
                                   status="COMPLETED")
        # order finalized but... simulate the race: is_ordered True with payment set
        o.payment = p; o.is_ordered = True; o.save()
        r = c.post("/orders/paypal/capture/",
                   json.dumps({"order_number": "O-88", "paypal_order_id": "PP-X"}),
                   content_type="application/json")
        self.assertEqual(r.json()["status"], "already_completed")


class StripeIsolationTests(TestCase):
    """Stripe must never fire while the shopper pays with PayPal."""

    def _tpl(self):
        import pathlib
        from django.conf import settings as dj
        return (pathlib.Path(dj.BASE_DIR) / "templates" / "orders" /
                "payments.html").read_text(encoding="utf-8")

    def test_stripe_mount_gated_on_readiness(self):
        t = self._tpl()
        self.assertIn("STRIPE_READY", t)
        self.assertIn("if (!STRIPE_READY) return;", t)
        self.assertIn("Card payments are not configured yet. Choose PayPal or contact us.", t)

    def test_reconciliation_wired_in_js(self):
        t = self._tpl()
        self.assertIn("ppReconcileThenError", t)
        self.assertIn("paypal_status", t)
        # the scary message only appears AFTER a reconciliation attempt
        self.assertNotIn("do NOT pay again — contact us and we will check it", t)
