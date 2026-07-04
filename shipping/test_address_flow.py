"""Professional Google address checkout flow — enforcement matrix tests.

Google is ALWAYS mocked. No real order side effects beyond the local test DB; no payment,
no capture, no refund, no mutative API.
"""
import time
from unittest.mock import MagicMock, patch

from django.core import signing
from django.test import Client, TestCase, override_settings

from shipping.address_validation import effective_mode, verify_for_order
from shipping.models import CheckoutApiConfig

FERNET_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="

GOOD = {"country": "IT", "postal_code": "20100", "city": "Milano",
        "address_line_1": "Via Roma 12"}


def _cfg(**kw):
    base = dict(is_enabled=True, enable_autocomplete=True, maps_browser_key="AIzaFAKE_b",
                validation_mode="strict")
    base.update(kw)
    return CheckoutApiConfig.objects.create(**base)


class EffectiveModeTests(TestCase):
    def test_disabled_when_no_config_or_off(self):
        self.assertEqual(effective_mode(None), "disabled")
        self.assertEqual(effective_mode(_cfg(is_enabled=False)), "disabled")

    def test_strict_degrades_to_warning_without_any_google_surface(self):
        cfg = _cfg(enable_autocomplete=False, maps_browser_key="")
        self.assertEqual(effective_mode(cfg), "warning")   # never lock every customer out

    def test_strict_kept_with_browser_surface(self):
        self.assertEqual(effective_mode(_cfg()), "strict")


class VerifyForOrderTests(TestCase):
    def test_missing_place_id_fails(self):
        ok, err = verify_for_order(_cfg(), GOOD, "")
        self.assertFalse(ok)
        self.assertIn("suggestions", str(err))

    def test_spoofed_claimed_verified_is_ignored(self):
        ok, _e = verify_for_order(_cfg(), GOOD, "", claimed_verified=True)
        self.assertFalse(ok)                                # hidden fields alone never pass

    def test_local_shape_failure_blocks(self):
        bad = dict(GOOD, postal_code="ABC")
        ok, _e = verify_for_order(_cfg(), bad, "pl_x")
        self.assertFalse(ok)

    def test_browser_trust_mode_without_server_key(self):
        ok, err = verify_for_order(_cfg(), GOOD, "pl_x")
        self.assertTrue(ok, err)                            # place_id + local checks

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_server_validation_ambiguous_blocks(self):
        cfg = _cfg(enable_address_validation=True)
        cfg.set_server_key("AIzaFAKE_server"); cfg.save()
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200, json=lambda: {
                "result": {"verdict": {"hasUnconfirmedComponents": True}}})
            ok, err = verify_for_order(cfg, GOOD, "pl_x")
        self.assertFalse(ok)
        self.assertIn("verified", str(err))

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_server_validation_failure_is_fail_closed(self):
        cfg = _cfg(enable_address_validation=True)
        cfg.set_server_key("AIzaFAKE_server"); cfg.save()
        with patch("requests.post", side_effect=Exception("net down")):
            ok, _e = verify_for_order(cfg, GOOD, "pl_x")
        self.assertFalse(ok)                                # strict never waves through on outage

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_server_validation_success_passes(self):
        cfg = _cfg(enable_address_validation=True)
        cfg.set_server_key("AIzaFAKE_server"); cfg.save()
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200, json=lambda: {"result": {"verdict": {}}})
            ok, err = verify_for_order(cfg, GOOD, "pl_x")
        self.assertTrue(ok, err)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class PlaceOrderModeTests(TestCase):
    """End-to-end place_order behaviour per mode (local test DB orders only)."""

    def _cart(self):
        from category.models import Category
        from store.models import Product
        from carts.models import Cart, CartItem
        cat, _ = Category.objects.get_or_create(category_name="Tees", slug="tees")
        p, _ = Product.objects.get_or_create(
            product_name="Test Tee", slug="test-tee", category=cat,
            defaults={"price": 25, "stock": 10, "is_available": True, "description": "t"})
        c = Client()
        c.get("/")
        cart, _x = Cart.objects.get_or_create(cart_id=c.session.session_key)
        CartItem.objects.create(product=p, cart=cart, quantity=1)
        return c

    def _post(self, c, extra=None):
        data = {
            "first_name": "Marco", "last_name": "Rossi", "email": "m@example.com",
            "phone": "333 1234567", "phone_prefix": "+39",
            "address_line_1": "Via Roma 12", "address_line_2": "",
            "country": "IT", "postal_code": "20100", "state": "MI", "city": "Milano",
            "order_note": "", "website": "",
            "form_ts": signing.dumps(time.time() - 10, salt="checkout-ts"),
            "google_place_id": "", "address_verified": "", "address_validation_source": "",
        }
        data.update(extra or {})
        return c.post("/orders/place_order/", data)

    def _orders(self):
        from orders.models import Order
        return Order.objects

    def test_strict_blocks_free_text_even_with_spoofed_hidden(self):
        _cfg(validation_mode="strict")
        c = self._cart()
        self._post(c, {"address_verified": "true"})         # spoof, no place_id
        self.assertEqual(self._orders().count(), 0)
        stash = c.session.get("checkout_restore") or {}
        self.assertIn("suggestions", stash.get("address_warning", ""))

    def test_strict_accepts_selected_place(self):
        _cfg(validation_mode="strict")                       # no server key -> browser-trust
        c = self._cart()
        r = self._post(c, {"google_place_id": "pl_ok", "address_verified": "true"})
        self.assertEqual(self._orders().count(), 1)
        o = self._orders().first()
        self.assertTrue(o.address_verified)
        self.assertEqual(o.google_place_id, "pl_ok")
        self.assertFalse(o.address_manual_confirmed)

    def test_warning_requires_explicit_confirmation(self):
        _cfg(validation_mode="warning")
        c = self._cart()
        self._post(c)                                        # manual, no confirm
        self.assertEqual(self._orders().count(), 0)
        r = self._post(c, {"address_confirmed": "1"})        # explicit confirm
        self.assertEqual(self._orders().count(), 1)
        o = self._orders().first()
        self.assertTrue(o.address_manual_confirmed)
        self.assertFalse(o.address_verified)

    def test_disabled_manual_flow_still_works(self):
        # no config at all -> disabled: plain manual entry passes local validation
        c = self._cart()
        self._post(c)
        self.assertEqual(self._orders().count(), 1)

    def test_checkout_renders_new_field_order_and_status(self):
        _cfg(validation_mode="strict")
        c = self._cart()
        html = c.get("/cart/checkout/").content.decode()
        self.assertLess(html.index('name="country"'), html.index('name="city"'))
        self.assertLess(html.index('name="city"'), html.index('name="address_line_1"'))
        self.assertIn("data-addr-placeid", html)
        self.assertIn('data-mode="strict"', html)
        self.assertIn("address-autocomplete.js", html)
