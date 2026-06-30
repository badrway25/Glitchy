"""Phase 65: luxury conversion + portal functional depth.

Focus on the real new feature — Buy again / Reorder — its safety (cart only, never an
order; ownership-scoped; original variations re-applied; unavailable products skipped),
plus the toast/feedback markup and the elevated empty states. No PII.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from store.models import Category, Product, Variation
from orders.models import Order, OrderProduct
from carts.models import CartItem


def _user(email, username):
    u = Account.objects.create_user(first_name="QA", last_name="T", username=username,
                                    email=email, password="x-test-pass")
    u.is_active = True
    u.save()
    return u


class Phase65ReorderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees65")
        cls.alice = _user("alice65@example.com", "alice65")
        cls.bob = _user("bob65@example.com", "bob65")
        cls.p = Product.objects.create(product_name="Reorder Tee", slug="reorder-tee-65", price=20,
                                       stock=5, category=cls.cat, is_available=True)
        cls.size = Variation.objects.create(product=cls.p, variation_category="size",
                                            variation_value="M", is_active=True)
        cls.gone = Product.objects.create(product_name="Gone Tee", slug="gone-tee-65", price=10,
                                          stock=0, category=cls.cat, is_available=False)
        cls.order = Order.objects.create(user=cls.alice, order_number="RE65", order_total=20, tax=0,
                                         status="Completed", is_ordered=True, first_name="QA",
                                         last_name="T", phone="0", email=cls.alice.email,
                                         address_line_1="x", country="IT", state="x", city="x")
        op = OrderProduct.objects.create(order=cls.order, user=cls.alice, product=cls.p, quantity=2,
                                         product_price=20, ordered=True)
        op.variations.add(cls.size)
        OrderProduct.objects.create(order=cls.order, user=cls.alice, product=cls.gone, quantity=1,
                                    product_price=10, ordered=True)

    def setUp(self):
        from django.utils import translation
        translation.activate("en")
        self.addCleanup(translation.deactivate_all)

    # -- reorder safety -------------------------------------------------------
    def test_reorder_adds_to_cart_with_variations(self):
        self.client.force_login(self.alice)
        r = self.client.post(reverse("order_reorder", args=["RE65"]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/")
        items = CartItem.objects.filter(user=self.alice)
        self.assertEqual(items.count(), 1)                 # only the available product
        ci = items.first()
        self.assertEqual(ci.quantity, 2)
        self.assertEqual(list(ci.variations.values_list("variation_value", flat=True)), ["M"])

    def test_reorder_never_creates_an_order(self):
        self.client.force_login(self.alice)
        before = Order.objects.count()
        self.client.post(reverse("order_reorder", args=["RE65"]))
        self.assertEqual(Order.objects.count(), before)    # no new order, no payment

    def test_reorder_requires_post(self):
        self.client.force_login(self.alice)
        r = self.client.get(reverse("order_reorder", args=["RE65"]))
        self.assertEqual(r.status_code, 405)               # GET not allowed

    def test_reorder_requires_login(self):
        r = self.client.post(reverse("order_reorder", args=["RE65"]))
        self.assertIn(r.status_code, (302, 301))
        self.assertIn("login", r.headers.get("Location", "").lower())

    def test_reorder_ownership(self):
        self.client.force_login(self.bob)
        r = self.client.post(reverse("order_reorder", args=["RE65"]))
        self.assertEqual(r.status_code, 404)               # not bob's order
        self.assertEqual(CartItem.objects.filter(user=self.bob).count(), 0)

    # -- markup / feedback ----------------------------------------------------
    def test_order_detail_buy_again_and_copy(self):
        self.client.force_login(self.alice)
        html = self.client.get(reverse("order_detail", args=["RE65"])).content.decode()
        self.assertIn("Buy again", html)
        self.assertIn(reverse("order_reorder", args=["RE65"]), html)   # the reorder form action
        self.assertIn("data-toast-label", html)            # copy → toast
        self.assertIn("csrfmiddlewaretoken", html)

    def test_toast_js_loaded(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("toast.js", html)
        self.assertIn('id="toastHost"', html)

    def test_orders_empty_state_present(self):
        # a fresh user with no orders sees the (now luxury) empty state
        u = _user("nobody65@example.com", "nobody65")
        self.client.force_login(u)
        html = self.client.get(reverse("my_orders")).content.decode()
        self.assertIn("dash-empty", html)

    # -- i18n + regressions ---------------------------------------------------
    def test_i18n(self):
        from django.utils import translation
        with translation.override("it"):
            self.assertEqual(translation.gettext("Buy again"), "Acquista di nuovo")
        with translation.override("fr"):
            self.assertEqual(translation.gettext("Order number copied"), "Numéro de commande copié")

    def test_checkout_redirect_regression(self):
        r = self.client.get("/checkout/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/cart/checkout/")
