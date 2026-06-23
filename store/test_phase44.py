"""Phase 44: complete-the-look, cart, variant validation, checkout, address delete, Printify audit."""
import json
import pathlib
from io import StringIO
from unittest import mock

from django.test import TestCase
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

from category.models import Category
from store.models import Product, Variation
from accounts.models import Account, Address

CSS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "css" / "premium.css"
JS = pathlib.Path(settings.BASE_DIR) / "greatkart" / "static" / "js" / "variant-guard.js"


def _product(name="Tee", color=True, size=True, **kw):
    cat = Category.objects.get_or_create(category_name="C", slug="c")[0]
    d = dict(product_name=name, slug=name.lower().replace(" ", "-"), description="x",
             price=25, stock=9999, category=cat, is_available=True)
    d.update(kw)
    p = Product.objects.create(**d)
    if color:
        Variation.objects.create(product=p, variation_category="color", variation_value="Black", is_active=True)
    if size:
        Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    return p


# ----------------------------------------------------------------- Complete the look
class CompleteLookTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_ctl_cards_equal_height(self):
        # flex column + height:100% + price margin-top:auto + title clamp
        self.assertIn(".ctl-card{position:relative;display:flex;flex-direction:column", self.css)
        self.assertIn("-webkit-line-clamp:2", self.css)

    def test_ymal_card_equal_height_hardened(self):
        self.assertIn("display:flex;flex-direction:column;height:100%", self.css)
        self.assertIn(".ymal-card .price{margin-top:auto;}", self.css)


# ----------------------------------------------------------------- Cart
class CartPageTests(TestCase):
    def test_cart_page_200(self):
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)

    def test_empty_cart_state(self):
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("cart-empty", html)

    def test_dark_cart_fixes_present(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".free-ship-bar{background:rgba(255,255,255,.12)", css)


# ----------------------------------------------------------------- Variant validation
class VariantValidationTests(TestCase):
    def setUp(self):
        self.p = _product("Guarded", color=True, size=True)
        self.add_url = reverse("add_cart", args=[self.p.id])

    def _cart_count(self):
        from carts.models import CartItem
        return CartItem.objects.count()

    def test_missing_both_blocks_add(self):
        resp = self.client.post(self.add_url, {})
        self.assertEqual(self._cart_count(), 0)             # nothing added
        self.assertRedirects(resp, self.p.get_url(), fetch_redirect_response=False)

    def test_missing_size_only_blocks_add(self):
        resp = self.client.post(self.add_url, {"color": "Black"})
        self.assertEqual(self._cart_count(), 0)
        self.assertRedirects(resp, self.p.get_url(), fetch_redirect_response=False)

    def test_missing_color_only_blocks_add(self):
        resp = self.client.post(self.add_url, {"size": "M"})
        self.assertEqual(self._cart_count(), 0)

    def test_complete_variant_adds(self):
        self.client.post(self.add_url, {"color": "Black", "size": "M"})
        self.assertEqual(self._cart_count(), 1)

    def test_one_size_product_adds_without_variants(self):
        p2 = _product("OneSize", color=False, size=False)
        self.client.post(reverse("add_cart", args=[p2.id]), {})
        from carts.models import CartItem
        self.assertTrue(CartItem.objects.filter(product=p2).exists())

    def test_pdp_has_guard_modal_and_i18n(self):
        html = self.client.get(self.p.get_url()).content.decode()
        self.assertIn('id="variantGuard"', html)
        self.assertIn('id="vgI18n"', html)
        self.assertIn("data-vg-wrap", html)

    def test_guard_js_loaded(self):
        html = self.client.get(self.p.get_url()).content.decode()
        self.assertIn("variant-guard.js", html)
        self.assertIn("stopImmediatePropagation", JS.read_text(encoding="utf-8"))


# ----------------------------------------------------------------- Checkout
class CheckoutTests(TestCase):
    def setUp(self):
        self.p = _product("CheckoutProd")

    def _add_item(self):
        self.client.post(reverse("add_cart", args=[self.p.id]), {"color": "Black", "size": "M"})

    def test_guest_checkout_200(self):
        self._add_item()
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 200)

    def test_checkout_has_country_and_summary(self):
        self._add_item()
        html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn('name="country"', html)
        self.assertIn("summary-card", html)


# ----------------------------------------------------------------- Saved address delete
class AddressDeleteTests(TestCase):
    def setUp(self):
        self.u = Account.objects.create_user(email="a@x.com", username="a", first_name="A",
                                             last_name="A", password="pw12345!")
        self.u.is_active = True; self.u.save()
        self.other = Account.objects.create_user(email="b@x.com", username="b", first_name="B",
                                                 last_name="B", password="pw12345!")
        self.other.is_active = True; self.other.save()
        self.addr = Address.objects.create(user=self.u, first_name="A", last_name="A",
                                           email="a@x.com", phone="1", address_line_1="L1",
                                           city="C", state="S", country="IT")

    def test_delete_requires_post(self):
        self.client.force_login(self.u)
        # GET must be rejected (405) — no more delete-via-GET
        resp = self.client.get(reverse("address_delete", args=[self.addr.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(Address.objects.filter(id=self.addr.id).exists())

    def test_owner_can_delete_via_post(self):
        self.client.force_login(self.u)
        self.client.post(reverse("address_delete", args=[self.addr.id]))
        self.assertFalse(Address.objects.filter(id=self.addr.id).exists())

    def test_cannot_delete_other_users_address(self):
        self.client.force_login(self.other)
        resp = self.client.post(reverse("address_delete", args=[self.addr.id]))
        self.assertEqual(resp.status_code, 404)             # scoped get_object_or_404
        self.assertTrue(Address.objects.filter(id=self.addr.id).exists())

    def test_set_default_requires_post(self):
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("address_set_default", args=[self.addr.id])).status_code, 405)

    def test_sidebar_has_addresses_link(self):
        self.client.force_login(self.u)
        html = self.client.get(reverse("address_list")).content.decode()
        # the sidebar now links to the addresses page (was only reachable by direct URL).
        # User has an address -> no empty-state -> the map-marker icon is the sidebar link only.
        self.assertIn(reverse("address_list"), html)
        self.assertIn('class="acc-link', html)
        self.assertIn("fa-map-marker-alt", html)


# ----------------------------------------------------------------- Printify data audit
class PrintifyAuditTests(TestCase):
    def setUp(self):
        self.p = _product("Synced", printify_product_id="PID6", printify_blueprint_id=145,
                          printify_provider_id=99, printify_provider_name="Prov",
                          printify_sync_status="synced")

    def test_json_output_valid_no_secrets(self):
        out = StringIO()
        call_command("printify_data_audit", "--product-id", str(self.p.id), "--json", stdout=out)
        data = json.loads(out.getvalue())
        self.assertIn("summary", data)
        self.assertIn("detail", data)
        self.assertNotIn("Bearer", out.getvalue())
        self.assertNotIn("PRINTIFY_API_TOKEN", out.getvalue())

    def test_classifies_cached_and_demo(self):
        out = StringIO()
        call_command("printify_data_audit", "--product-id", str(self.p.id), "--json", stdout=out)
        data = json.loads(out.getvalue())
        fields = {f["field"]: f["classification"] for f in data["detail"][0]["fields"]}
        self.assertEqual(fields["printify_product_id"], "cached_from_db")
        self.assertEqual(fields["stock"], "demo")           # 9999 placeholder

    def test_compare_site_flags_fallback_shipping(self):
        out = StringIO()
        call_command("printify_data_audit", "--product-id", str(self.p.id),
                     "--compare-site", "--json", stdout=out)
        data = json.loads(out.getvalue())
        fields = {f["field"]: f["classification"] for f in data["detail"][0]["fields"]}
        # SHIPPING_USE_PRINTIFY is False in tests -> shipping is demo/fallback, not real
        self.assertIn(fields.get("site:shipping_source"), ("demo", "fallback"))

    def test_live_mismatch_detected_mocked(self):
        # mock the Printify client to return a different variant set -> mismatch
        fake = mock.MagicMock()
        fake.get_product.return_value = {"title": "Synced", "visible": True,
                                         "variants": [{"is_enabled": True}] * 50}
        out = StringIO()
        with mock.patch("printify_integration.printify_client.get_client", return_value=fake):
            with self.assertRaises(SystemExit) as ctx:   # exit 2 on mismatch
                call_command("printify_data_audit", "--product-id", str(self.p.id),
                             "--live", "--json", stdout=out)
            self.assertEqual(ctx.exception.code, 2)
