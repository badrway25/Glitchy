"""Smart localized shipping + premium checkout validation — phase tests.

External APIs are MOCKED (no Google call, no payment, no order side effects).
"""
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from shipping.localization import localize_shipping
from shipping.models import CheckoutApiConfig

FERNET_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
GOOGLE_KEY = "AIzaFAKE_server_key_do_not_leak_7777"


class _Req:
    """Minimal request stub for localize_shipping."""
    def __init__(self, session=None, meta=None):
        self.session = session if session is not None else {}
        self.META = meta or {}
        self.headers = {}


class LocalizationTests(TestCase):
    def test_unknown_destination_is_neutral_never_invented(self):
        d = localize_shipping(_Req())
        self.assertFalse(d["known"])
        self.assertEqual(d["source"], "default")
        self.assertNotIn("Ships to", d["line_label"])       # no invented destination
        self.assertEqual(d["shipping_cost_label"], "")       # no invented cost
        self.assertEqual(d["eta_label"], "")                 # no invented days

    def test_manual_session_country_wins_with_real_rate(self):
        d = localize_shipping(_Req(session={"ship_country": "FR"}), subtotal=25)
        self.assertTrue(d["known"])
        self.assertEqual(d["source"], "manual")
        self.assertEqual(d["country_code"], "FR")
        self.assertIn("France", d["line_label"])
        self.assertIn("business days", d["line_label"])      # real table days

    def test_header_detection_used(self):
        d = localize_shipping(_Req(meta={"HTTP_CF_IPCOUNTRY": "DE"}), subtotal=25)
        self.assertEqual(d["source"], "header")
        self.assertIn("Germany", d["line_label"])

    def test_uncurated_country_falls_back_to_neutral(self):
        d = localize_shipping(_Req(meta={"HTTP_CF_IPCOUNTRY": "BR"}))
        self.assertTrue(d["is_fallback"])
        self.assertNotIn("BR", d["line_label"])

    def test_free_threshold_reflected_when_configured(self):
        d = localize_shipping(_Req(session={"ship_country": "FR"}), subtotal=100000)
        self.assertTrue(d["free"])
        self.assertIn("Free shipping", d["line_label"])

    def test_set_country_endpoint_validates_and_localizes(self):
        c = Client()
        r = c.post("/shipping/set-country/", {"country": "x1"},
                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 400)                 # invalid code rejected
        r = c.post("/shipping/set-country/", {"country": "FR", "subtotal": "25"},
                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertIn("France", data["localized"]["line_label"])


class PhoneValidationTests(TestCase):
    def _form(self, phone, prefix="+39", country="IT"):
        from orders.forms import OrderForm
        return OrderForm({
            "first_name": "Marco", "last_name": "Rossi", "email": "m@example.com",
            "phone": phone, "phone_prefix": prefix,
            "address_line_1": "Via Roma 1", "address_line_2": "",
            "country": country, "postal_code": "20100", "state": "MI", "city": "Milano",
            "order_note": "",
        })

    def test_valid_national_number_normalized_to_e164(self):
        f = self._form("333 1234567")
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["phone"], "+393331234567")

    def test_already_international_number_kept(self):
        f = self._form("+33 6 12 34 56 78", prefix="+39", country="IT")
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["phone"], "+33612345678")

    def test_too_short_rejected(self):
        f = self._form("12")
        self.assertFalse(f.is_valid())
        self.assertIn("phone", f.errors)

    def test_letters_rejected(self):
        f = self._form("33x1234567")
        self.assertFalse(f.is_valid())
        self.assertIn("phone", f.errors)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class AntiBotAndPreservationTests(TestCase):
    def _cart(self, client):
        from category.models import Category
        from store.models import Product
        from carts.models import Cart, CartItem
        cat, _ = Category.objects.get_or_create(category_name="Tees", slug="tees")
        p, _ = Product.objects.get_or_create(
            product_name="Test Tee", slug="test-tee", category=cat,
            defaults={"price": 25, "stock": 10, "is_available": True, "description": "t"})
        client.get("/")                                    # create a session
        session_key = client.session.session_key
        cart, _c = Cart.objects.get_or_create(cart_id=session_key)
        CartItem.objects.create(product=p, cart=cart, quantity=1)
        return p

    def _post(self, client, extra=None, ts_age=10):
        from django.core import signing
        import time
        data = {
            "first_name": "Marco", "last_name": "Rossi", "email": "m@example.com",
            "phone": "bad", "phone_prefix": "+39",
            "address_line_1": "Via Roma 1", "address_line_2": "",
            "country": "IT", "postal_code": "20100", "state": "MI", "city": "Milano",
            "order_note": "", "website": "",
            "form_ts": signing.dumps(time.time() - ts_age, salt="checkout-ts"),
        }
        data.update(extra or {})
        return client.post("/orders/place_order/", data)

    def test_honeypot_blocks_bot(self):
        from category.models import Category
        c = Client()
        self._cart(c)
        r = self._post(c, extra={"website": "spam.example"})
        self.assertEqual(r.status_code, 302)               # generic redirect, no order created
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)

    def test_too_fast_submission_blocked(self):
        c = Client()
        self._cart(c)
        r = self._post(c, ts_age=0.5)
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_phone_preserves_fields_in_session(self):
        c = Client()
        self._cart(c)
        self._post(c)                                      # phone "bad" -> invalid
        stash = c.session.get("checkout_restore")
        self.assertIsNotNone(stash)
        self.assertEqual(stash["data"]["first_name"], "Marco")
        self.assertEqual(stash["data"]["address_line_1"], "Via Roma 1")
        self.assertIn("phone", stash["errors"])
        # checkout re-render restores the values inline
        html = c.get("/cart/checkout/").content.decode()
        self.assertIn('value="Marco"', html)
        self.assertIn('value="Via Roma 1"', html)


@override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY,
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class CheckoutApiConfigTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import Account
        cls.su = Account.objects.create_superuser("Adm", "User", "adm@x.com", "adm", "pw-Str0ng!123")
        cls.staff = Account.objects.create_user("St", "Aff", "st@x.com", "st", "pw-Str0ng!123")
        cls.staff.is_staff = True; cls.staff.is_admin = True; cls.staff.save()

    def test_server_key_encrypted_and_masked_not_leaked(self):
        cfg = CheckoutApiConfig()
        cfg.set_server_key(GOOGLE_KEY, by="adm")
        cfg.save()
        self.assertNotIn(GOOGLE_KEY, cfg.server_key_ciphertext)
        self.assertEqual(cfg.get_server_key(), GOOGLE_KEY)
        self.assertIn("7777", cfg.server_key_display())
        self.client.force_login(self.su)
        html = self.client.get(f"/admin/shipping/checkoutapiconfig/{cfg.id}/change/").content.decode()
        self.assertNotIn(GOOGLE_KEY, html)
        self.assertIn("7777", html)                        # masked last-4 only

    def test_non_superuser_cannot_test_or_see_key_field(self):
        cfg = CheckoutApiConfig(); cfg.set_server_key(GOOGLE_KEY, by="a"); cfg.save()
        self.client.force_login(self.staff)
        html = self.client.get(f"/admin/shipping/checkoutapiconfig/{cfg.id}/change/").content.decode()
        self.assertNotIn("new_server_key", html)
        r = self.client.post(f"/admin/shipping/checkoutapiconfig/{cfg.id}/test-connection/")
        self.assertIn(r.status_code, (302, 403))           # denied either way
        cfg.refresh_from_db()
        self.assertEqual(cfg.last_connection_status, "")    # the check never ran

    def test_test_connection_is_readonly_and_mocked(self):
        cfg = CheckoutApiConfig(); cfg.set_server_key(GOOGLE_KEY, by="a"); cfg.save()
        from shipping import address_validation as av
        with patch.object(av, "test_connection", wraps=av.test_connection):
            with patch("requests.post") as post:
                post.return_value = MagicMock(status_code=200, json=lambda: {"result": {}})
                post.return_value.raise_for_status = lambda: None
                res = av.test_connection(cfg)
        self.assertTrue(res["ok"])
        cfg.refresh_from_db()
        self.assertEqual(cfg.last_connection_status, "connected")

    def test_validation_warning_only_and_fail_open(self):
        from shipping.address_validation import validate_address
        cfg = CheckoutApiConfig(is_enabled=True, enable_address_validation=True)
        cfg.set_server_key(GOOGLE_KEY, by="a"); cfg.save()
        data = {"country": "IT", "postal_code": "20100", "city": "Milano",
                "address_line_1": "Via Roma 1"}
        with patch("requests.post") as post:
            post.return_value = MagicMock(status_code=200, json=lambda: {
                "result": {"verdict": {"hasUnconfirmedComponents": True}}})
            level, msg = validate_address(data, cfg)
        self.assertEqual(level, "warning")                 # warning, never a hard block
        with patch("requests.post", side_effect=Exception("net down")):
            level, _msg = validate_address(data, cfg)
        self.assertEqual(level, "ok")                      # fail-open

    def test_local_postal_shape_warning(self):
        from shipping.address_validation import validate_locally
        level, _m = validate_locally({"country": "IT", "postal_code": "ABC",
                                      "address_line_1": "Via Roma 1"})
        self.assertEqual(level, "warning")

    def test_autocomplete_hidden_when_not_configured(self):
        html = Client().get("/").content.decode()          # sanity: no Google script site-wide
        self.assertNotIn("maps.googleapis.com", html)
