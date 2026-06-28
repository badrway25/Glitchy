"""Phase 53: end-to-end customer journeys + portal security.

All data is fictitious QA/TEST data. No real orders, no real payments
(Stripe/Printify are never hit — orders are created directly as test fixtures and
the shipping estimate uses the local fallback with SHIPPING_USE_PRINTIFY off).
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import Account, Address
from carts.models import Cart, CartItem
from category.models import Category
from orders.models import Order, OrderProduct
from store.models import Product, Variation

# Fictitious QA customers across countries (label makes the test origin obvious).
QA_CUSTOMERS = [
    {"email": "qa.brussels@example.test", "first": "Bram", "last": "QA-BE",
     "city": "Bruxelles", "postal": "1000", "country": "BE"},
    {"email": "qa.milano@example.test", "first": "Marco", "last": "QA-IT",
     "city": "Milano", "postal": "20100", "country": "IT"},
    {"email": "qa.paris@example.test", "first": "Camille", "last": "QA-FR",
     "city": "Paris", "postal": "75001", "country": "FR"},
    {"email": "qa.newyork@example.test", "first": "Jordan", "last": "QA-US",
     "city": "New York", "postal": "10001", "country": "US"},
]
UNSUPPORTED = {"city": "Casablanca", "postal": "20000", "country": "MA"}


def make_user(email, first="QA", last="Test"):
    u = Account.objects.create_user(first_name=first, last_name=last,
                                    username=email.split("@")[0], email=email, password="QaPw!2026x")
    u.is_active = True
    u.save()
    return u


def make_product(name="QA Tee", price=20):
    cat = Category.objects.get_or_create(category_name="QA Cat", slug="qa-cat")[0]
    p = Product.objects.create(product_name=name, slug=name.lower().replace(" ", "-"),
                               description="x", price=price, stock=9999, category=cat,
                               is_available=True, printify_product_id="qa-shop-1",
                               printify_blueprint_id=145, printify_provider_id=29)
    Variation.objects.create(product=p, variation_category="color", variation_value="Black",
                             is_active=True, printify_variant_id="17887", printify_is_default=True)
    Variation.objects.create(product=p, variation_category="size", variation_value="M", is_active=True)
    return p


def make_order(user, product, number, country="IT", status="Completed", with_payment=True):
    from orders.models import Payment
    payment = None
    if with_payment:
        payment = Payment.objects.create(user=user, payment_id=f"TESTPAY-{number}",
                                         payment_method="Stripe (TEST)", amount_paid="40.00",
                                         status="Completed")
    o = Order.objects.create(
        user=user, payment=payment, order_number=number,
        first_name=user.first_name, last_name=user.last_name, phone="+32470000000",
        email=user.email, address_line_1="Rue QA 1", country=country, state="QA",
        city="QA City", postal_code="1000", currency="EUR", items_subtotal=40.0,
        shipping_cost=4.9, order_total=46.78, tax=1.88, status=status,
        is_ordered=True, language_code="en", shipping_min_days=7, shipping_max_days=12)
    OrderProduct.objects.create(order=o, user=user, product=product, quantity=2,
                                product_price=20.0, ordered=True)
    return o


# --------------------------------------------------------------------------- #
# E2E journeys per country
# --------------------------------------------------------------------------- #
@override_settings(SHIPPING_USE_PRINTIFY=False, SHIPPING_FREE_THRESHOLD=0)
class CustomerJourneyTests(TestCase):
    def setUp(self):
        self.product = make_product()

    def _journey(self, cust):
        user = make_user(cust["email"], cust["first"], cust["last"])
        self.client.force_login(user)

        # 1) Add a delivery address (supported country).
        r = self.client.post(reverse("address_create"), {
            "first_name": cust["first"], "last_name": cust["last"], "email": cust["email"],
            "phone": "+32 470 00 00 00", "address_line_1": "Rue QA 1", "address_line_2": "",
            "city": cust["city"], "state": "QA", "postal_code": cust["postal"],
            "country": cust["country"], "is_default": "on"})
        self.assertEqual(r.status_code, 302)  # saved -> redirect
        self.assertTrue(Address.objects.filter(user=user, country=cust["country"]).exists())

        # 2) Cart + shipping estimate.
        cart = Cart.objects.create(cart_id=f"e2e-{cust['country']}")
        CartItem.objects.create(product=self.product, user=user, quantity=2, is_active=True)
        est = self.client.post(reverse("shipping_estimate"),
                               {"country": cust["country"], "postal_code": cust["postal"]}).json()
        self.assertTrue(est["available"], cust["country"])
        self.assertIn(est["source"], ("local_fallback", "cached_profile", "live_printify"))

        # 3) An order exists -> portal pages render.
        order = make_order(user, self.product, f"E2E{cust['country']}1", country=cust["country"])
        for url in (reverse("dashboard"), reverse("my_orders"), reverse("billing"),
                    reverse("order_detail", args=[order.order_number])):
            self.assertEqual(self.client.get(url).status_code, 200, url)

        # 4) Receipt PDF (download + inline preview).
        pdf = self.client.get(reverse("invoice_pdf", args=[order.order_number]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content[:5] == b"%PDF-")
        self.assertIn("attachment", pdf["Content-Disposition"])
        inline = self.client.get(reverse("invoice_pdf", args=[order.order_number]) + "?disposition=inline")
        self.assertIn("inline", inline["Content-Disposition"])

        # 5) Order search finds it.
        found = self.client.get(reverse("my_orders") + f"?q={order.order_number}")
        self.assertContains(found, order.order_number)

        # 6) Wishlist add + saved page.
        import json as _json
        self.client.post(reverse("wishlist:toggle"), data=_json.dumps({"product_id": self.product.id}),
                         content_type="application/json")
        self.assertEqual(self.client.get(reverse("wishlist:saved")).status_code, 200)

        # 7) Delete the address.
        addr = Address.objects.filter(user=user).first()
        self.client.post(reverse("address_delete", args=[addr.id]))
        self.assertFalse(Address.objects.filter(id=addr.id).exists())
        self.client.logout()

    def test_be_journey(self):
        self._journey(QA_CUSTOMERS[0])

    def test_it_journey(self):
        self._journey(QA_CUSTOMERS[1])

    def test_fr_journey(self):
        self._journey(QA_CUSTOMERS[2])

    def test_us_journey(self):
        self._journey(QA_CUSTOMERS[3])


@override_settings(SHIPPING_USE_PRINTIFY=False)
class UnsupportedCountryTests(TestCase):
    def setUp(self):
        self.user = make_user("qa.ma@example.test")
        self.client.force_login(self.user)
        self.product = make_product()

    def test_unsupported_country_estimate_unavailable(self):
        CartItem.objects.create(product=self.product, user=self.user, quantity=1, is_active=True)
        est = self.client.post(reverse("shipping_estimate"),
                               {"country": UNSUPPORTED["country"], "postal_code": UNSUPPORTED["postal"]}).json()
        self.assertFalse(est["available"])
        self.assertIn("country_unsupported", est["errors_safe"])

    def test_address_form_rejects_unsupported_country(self):
        # MA is not in the curated country choices -> form rejects it.
        r = self.client.post(reverse("address_create"), {
            "first_name": "QA", "last_name": "MA", "email": "qa.ma@example.test",
            "phone": "+212600000000", "address_line_1": "Rue Test", "city": "Casablanca",
            "state": "QA", "postal_code": "20000", "country": "MA"})
        self.assertEqual(r.status_code, 200)  # re-render with error, not redirect
        self.assertFalse(Address.objects.filter(user=self.user, country="MA").exists())


# --------------------------------------------------------------------------- #
# Security / data isolation
# --------------------------------------------------------------------------- #
class PortalSecurityTests(TestCase):
    def setUp(self):
        self.product = make_product()
        self.a = make_user("qa.a@example.test", "Alice", "QA")
        self.b = make_user("qa.b@example.test", "Bob", "QA")
        self.order_b = make_order(self.b, self.product, "SECB1")
        self.addr_b = Address.objects.create(user=self.b, first_name="Bob", last_name="QA",
                                             email="qa.b@example.test", phone="+320000",
                                             address_line_1="B St", city="Bxl", state="QA",
                                             postal_code="1000", country="BE")

    def test_portal_requires_login(self):
        for name in ("dashboard", "my_orders", "billing", "address_list"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r["Location"])

    def test_cannot_view_other_users_order(self):
        self.client.force_login(self.a)
        r = self.client.get(reverse("order_detail", args=[self.order_b.order_number]))
        self.assertEqual(r.status_code, 404)

    def test_cannot_download_other_users_receipt(self):
        self.client.force_login(self.a)
        r = self.client.get(reverse("invoice_pdf", args=[self.order_b.order_number]))
        self.assertEqual(r.status_code, 403)

    def test_cannot_delete_other_users_address(self):
        self.client.force_login(self.a)
        r = self.client.post(reverse("address_delete", args=[self.addr_b.id]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Address.objects.filter(id=self.addr_b.id).exists())

    def test_order_list_shows_only_own(self):
        order_a = make_order(self.a, self.product, "SECA1")
        self.client.force_login(self.a)
        html = self.client.get(reverse("my_orders")).content.decode()
        self.assertIn(order_a.order_number, html)
        self.assertNotIn(self.order_b.order_number, html)

    def test_billing_shows_only_own(self):
        order_a = make_order(self.a, self.product, "SECA2")
        self.client.force_login(self.a)
        html = self.client.get(reverse("billing")).content.decode()
        self.assertIn(order_a.order_number, html)
        self.assertNotIn(self.order_b.order_number, html)


# --------------------------------------------------------------------------- #
# Receipts (PDF) + i18n
# --------------------------------------------------------------------------- #
class ReceiptPdfTests(TestCase):
    def setUp(self):
        self.user = make_user("qa.pdf@example.test")
        self.product = make_product()
        self.order = make_order(self.user, self.product, "PDF1")
        self.client.force_login(self.user)

    def test_receipt_downloads_as_pdf(self):
        r = self.client.get(reverse("invoice_pdf", args=[self.order.order_number]))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content[:5] == b"%PDF-")
        self.assertIn("receipt_", r["Content-Disposition"])

    def test_receipt_builds_in_three_languages(self):
        from orders.receipt_pdf import build_receipt_pdf
        items = OrderProduct.objects.filter(order=self.order).select_related("product")
        sizes = set()
        for lang in ("en", "it", "fr"):
            self.order.language_code = lang
            pdf = build_receipt_pdf(self.order, items)
            self.assertTrue(pdf[:5] == b"%PDF-")
            sizes.add(len(pdf))
        # localized labels differ -> at least two distinct byte lengths
        self.assertGreaterEqual(len(sizes), 2)

    def test_receipt_omits_internal_cost_fields(self):
        # Set internal costs; they must never reach the customer PDF text stream.
        self.order.cost_production = 999.0
        self.order.cost_shipping = 888.0
        self.order.payment_fee = 77.0
        self.order.printify_order_id = "PF-INTERNAL-123"
        self.order.save()
        from orders.receipt_pdf import build_receipt_pdf
        items = OrderProduct.objects.filter(order=self.order).select_related("product")
        pdf = build_receipt_pdf(self.order, items)
        # crude scan of the (uncompressed text) stream for the secret markers
        blob = bytes(pdf)
        self.assertNotIn(b"PF-INTERNAL-123", blob)
        self.assertNotIn(b"999.0", blob)


# --------------------------------------------------------------------------- #
# Order list filters
# --------------------------------------------------------------------------- #
class OrderListFilterTests(TestCase):
    def setUp(self):
        self.user = make_user("qa.filter@example.test")
        self.client.force_login(self.user)
        self.p1 = make_product("Alpha Tee")
        self.o1 = make_order(self.user, self.p1, "FILT1", status="Completed")
        self.o2 = make_order(self.user, self.p1, "FILT2", status="Cancelled")

    def test_search_by_order_number(self):
        html = self.client.get(reverse("my_orders") + "?q=FILT1").content.decode()
        self.assertIn("FILT1", html)
        self.assertNotIn("FILT2", html)

    def test_search_by_product_name(self):
        html = self.client.get(reverse("my_orders") + "?q=Alpha").content.decode()
        self.assertIn("FILT1", html)

    def test_status_filter(self):
        html = self.client.get(reverse("my_orders") + "?status=Cancelled").content.decode()
        self.assertIn("FILT2", html)
        self.assertNotIn("FILT1", html)

    def test_invalid_sort_is_ignored(self):
        r = self.client.get(reverse("my_orders") + "?sort=__dangerous__")
        self.assertEqual(r.status_code, 200)  # whitelist -> falls back to default


# --------------------------------------------------------------------------- #
# Address validation + registration view
# --------------------------------------------------------------------------- #
class AddressValidationTests(TestCase):
    def setUp(self):
        self.user = make_user("qa.addr@example.test")
        self.client.force_login(self.user)

    def _post(self, **over):
        data = {"first_name": "QA", "last_name": "Test", "email": "qa.addr@example.test",
                "phone": "+32 470 00 00 00", "address_line_1": "Rue QA 1", "address_line_2": "",
                "city": "Bruxelles", "state": "QA", "postal_code": "1000", "country": "BE"}
        data.update(over)
        return self.client.post(reverse("address_create"), data)

    def test_valid_address_created(self):
        self.assertEqual(self._post().status_code, 302)
        self.assertTrue(Address.objects.filter(user=self.user, city="Bruxelles").exists())

    def test_missing_city_rejected(self):
        r = self._post(city="")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Address.objects.filter(user=self.user, postal_code="1000", city="").exists())

    def test_missing_postal_rejected(self):
        r = self._post(postal_code="")
        self.assertEqual(r.status_code, 200)

    def test_bad_phone_rejected(self):
        r = self._post(phone="not-a-phone!!")
        self.assertEqual(r.status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationFlowTests(TestCase):
    def test_register_creates_inactive_user_and_redirects(self):
        with translation.override("en"):
            r = self.client.post(reverse("register"), {
                "first_name": "New", "last_name": "QA", "phone_number": "+32470000000",
                "email": "qa.new@example.test", "password": "QaPw!2026x",
                "confirm_password": "QaPw!2026x"})
        self.assertEqual(r.status_code, 302)
        u = Account.objects.filter(email="qa.new@example.test").first()
        self.assertIsNotNone(u)
        self.assertFalse(u.is_active)  # email verification required
