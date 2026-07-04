"""Fix-phase tests: single phone-prefix selector + PAYMENT_CONFIG_KEY admin UX.

No Google calls, no orders, no payments — everything local/mocked.
"""
import pathlib

from django.conf import settings
from django.test import Client, TestCase, override_settings

from shipping.models import CheckoutApiConfig

FERNET_KEY = "kGBvwlS8IzxkmQbvY7mE-z3gcyIPhJYMKMYIM3mrYC8="
GOOGLE_KEY = "AIzaFAKE_test_key_9999"
BASE = pathlib.Path(settings.BASE_DIR)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class SinglePrefixSelectorTests(TestCase):
    def _checkout_html(self):
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
        return c.get("/cart/checkout/").content.decode()

    def test_exactly_one_prefix_select_with_pmsel_opt_out(self):
        html = self._checkout_html()
        self.assertEqual(html.count('name="phone_prefix"'), 1)
        # the native select MUST opt out of premium-select.js, or a second flagless
        # .pmsel-btn renders next to the flag dropdown (the shipped duplicate-selector bug)
        import re
        sel = re.search(r'<select[^>]*name="phone_prefix"[^>]*>', html).group(0)
        self.assertIn("data-no-enhance", sel)
        self.assertIn("data-pfx-select", sel)

    def test_defensive_layers_present(self):
        js = (BASE / "greatkart" / "static" / "js" / "store-features.js").read_text(encoding="utf-8")
        self.assertIn('select.closest(".pmsel")', js)      # hides a cached-JS pmsel wrapper
        css = (BASE / "greatkart" / "static" / "css" / "premium.css").read_text(encoding="utf-8")
        self.assertIn(":not([hidden]) ~ .pmsel", css)      # CSS belt-and-braces


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ConfigKeyAdminUXTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import Account
        cls.su = Account.objects.create_superuser("Adm", "User", "adm2@x.com", "adm2", "pw-Str0ng!123")

    @override_settings(PAYMENT_CONFIG_KEY="")
    def test_missing_key_never_saves_plaintext_and_warns(self):
        from shipping.admin import CheckoutApiConfigForm
        form = CheckoutApiConfigForm({
            "is_enabled": False, "enable_autocomplete": False, "enable_address_validation": False,
            "maps_browser_key": "", "allowed_domains_note": "", "new_server_key": GOOGLE_KEY,
        })
        self.assertFalse(form.is_valid())
        err = str(form.errors["new_server_key"])
        self.assertIn("PAYMENT_CONFIG_KEY", err)           # actionable
        self.assertNotIn(GOOGLE_KEY, err)                  # never echoes the key
        self.assertEqual(CheckoutApiConfig.objects.count(), 0)

    @override_settings(PAYMENT_CONFIG_KEY="")
    def test_admin_page_shows_premium_warning_card(self):
        cfg = CheckoutApiConfig.objects.create()
        self.client.force_login(self.su)
        html = self.client.get(f"/admin/shipping/checkoutapiconfig/{cfg.id}/change/").content.decode()
        self.assertIn("Encryption key missing", html)
        self.assertIn("PAYMENT_CONFIG_KEY", html)
        self.assertNotIn(GOOGLE_KEY, html)

    @override_settings(PAYMENT_CONFIG_KEY=FERNET_KEY)
    def test_with_key_saved_encrypted_and_masked(self):
        cfg = CheckoutApiConfig.objects.create()
        cfg.set_server_key(GOOGLE_KEY, by="adm")
        cfg.save()
        self.assertNotIn(GOOGLE_KEY, cfg.server_key_ciphertext)
        self.assertEqual(cfg.get_server_key(), GOOGLE_KEY)
        self.assertIn("9999", cfg.server_key_display())
        self.client.force_login(self.su)
        html = self.client.get(f"/admin/shipping/checkoutapiconfig/{cfg.id}/change/").content.decode()
        self.assertNotIn("Encryption key missing", html)   # card hidden when ready
        self.assertNotIn(GOOGLE_KEY, html)
