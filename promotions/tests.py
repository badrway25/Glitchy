from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import Coupon


class CouponValidationTests(TestCase):
    def test_percentage_discount(self):
        c = Coupon.objects.create(code="ten", discount_type="percent", value=Decimal("10"))
        self.assertEqual(c.code, "TEN")  # normalised to upper
        ok, reason = c.validate(100)
        self.assertTrue(ok)
        self.assertEqual(c.discount_for(100), Decimal("10.00"))

    def test_fixed_discount_never_exceeds_subtotal(self):
        c = Coupon.objects.create(code="big", discount_type="fixed", value=Decimal("50"))
        self.assertEqual(c.discount_for(30), Decimal("30.00"))  # capped at subtotal

    def test_inactive_rejected(self):
        c = Coupon.objects.create(code="off", value=Decimal("10"), is_active=False)
        ok, reason = c.validate(100)
        self.assertFalse(ok)
        self.assertEqual(reason, "inactive")

    def test_expired_rejected(self):
        c = Coupon.objects.create(code="old", value=Decimal("10"),
                                  valid_to=timezone.now() - timedelta(days=1))
        ok, reason = c.validate(100)
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")

    def test_not_started_rejected(self):
        c = Coupon.objects.create(code="soon", value=Decimal("10"),
                                  valid_from=timezone.now() + timedelta(days=1))
        self.assertEqual(c.validate(100)[1], "not_started")

    def test_min_order_enforced(self):
        c = Coupon.objects.create(code="min50", value=Decimal("5"),
                                  discount_type="fixed", min_order_amount=Decimal("50"))
        self.assertEqual(c.validate(40)[1], "min_order")
        self.assertTrue(c.validate(60)[0])

    def test_usage_limit_enforced(self):
        c = Coupon.objects.create(code="once", value=Decimal("10"), usage_limit=1)
        c.used_count = 1
        c.save()
        self.assertEqual(c.validate(100)[1], "used_up")


class CouponServiceTests(TestCase):
    def setUp(self):
        from django.test import Client
        self.client = Client(enforce_csrf_checks=False)
        Coupon.objects.create(code="WELCOME10", discount_type="percent", value=Decimal("10"))

    def _req(self):
        from django.contrib.sessions.backends.db import SessionStore

        class Req:
            session = SessionStore()
        return Req()

    def test_apply_invalid_code(self):
        from .services import apply
        r = apply(self._req(), "NOPE", 100)
        self.assertFalse(r["ok"])

    def test_apply_valid_code(self):
        from .services import apply, applied_coupon
        req = self._req()
        r = apply(req, "welcome10", 100)
        self.assertTrue(r["ok"])
        self.assertEqual(r["discount"], "10.00")
        # re-validates from session
        coupon, disc = applied_coupon(req, 100)
        self.assertEqual(disc, Decimal("10.00"))


class CouponPerUserTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        Coupon.objects.create(code="ONCE", discount_type="percent", value=Decimal("10"),
                              per_user_limit=1)

    def _user_req(self, email="u@example.com"):
        from django.contrib.sessions.backends.db import SessionStore
        u = self.User.objects.create_user(email=email, first_name="U", last_name="U",
                                           username=email.split("@")[0], password="pw12345!")
        u.is_active = True; u.save()

        class Req:
            user = u
            session = SessionStore()
        return Req()

    def test_one_time_per_user_blocks_second_use(self):
        from .models import CouponRedemption
        from .services import apply
        req = self._user_req()
        # first use ok
        self.assertTrue(apply(req, "ONCE", 100)["ok"])
        # record a redemption for this user
        c = Coupon.objects.get(code="ONCE")
        CouponRedemption.objects.create(coupon=c, user=req.user, amount=Decimal("10"))
        # second use rejected (already used)
        r = apply(req, "ONCE", 100)
        self.assertFalse(r["ok"])
        self.assertIn("already used", r["message"].lower())

    def test_guest_session_one_time(self):
        from django.contrib.sessions.backends.db import SessionStore
        from .models import CouponRedemption
        from .services import apply

        class Anon:
            is_authenticated = False

        class Req:
            user = Anon()
            session = SessionStore()
        req = Req()
        req.session.save()
        c = Coupon.objects.get(code="ONCE")
        self.assertTrue(apply(req, "ONCE", 100)["ok"])
        CouponRedemption.objects.create(coupon=c, session_key=req.session.session_key,
                                        amount=Decimal("10"))
        self.assertFalse(apply(req, "ONCE", 100)["ok"])


class CouponRedemptionRecordTests(TestCase):
    """Redemption is deferred to the PAID state; finalize is atomic + idempotent."""
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.coupon = Coupon.objects.create(code="REC", discount_type="percent",
                                            value=Decimal("10"), per_user_limit=1)

    def _user(self):
        u = self.User.objects.create_user(email="r@example.com", first_name="R",
                                          last_name="R", username="r", password="pw12345!")
        u.is_active = True; u.save()
        return u

    def _req(self):
        from django.contrib.sessions.backends.db import SessionStore
        sess = SessionStore(); sess["coupon_code"] = "REC"; sess.save()

        class Req:
            pass
        req = Req(); req.user = self._user(); req.session = sess
        return req

    def _order(self, user, number="OREC"):
        from orders.models import Order
        return Order.objects.create(user=user, first_name="R", last_name="R", phone="1",
                                    email=user.email, address_line_1="x", city="c", state="s",
                                    country="US", order_total=90, tax=0, ip="127.0.0.1",
                                    order_number=number, coupon_code="REC", discount=10,
                                    is_ordered=True)

    def test_quote_does_not_record_redemption(self):
        # At place_order we only validate + return the discount; NO redemption yet.
        from .models import CouponRedemption
        from .services import quote_for_order, SESSION_KEY
        req = self._req()
        code, disc = quote_for_order(req, 100)
        self.assertEqual(code, "REC")
        self.assertEqual(disc, Decimal("10.00"))
        self.assertNotIn(SESSION_KEY, req.session)   # bound to the order now
        self.assertEqual(CouponRedemption.objects.count(), 0)   # not burned yet

    def test_finalize_records_once_and_is_idempotent(self):
        from .models import CouponRedemption
        from .services import finalize_coupon_redemption
        order = self._order(self._user())
        finalize_coupon_redemption(order)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)
        self.assertEqual(CouponRedemption.objects.filter(coupon=self.coupon).count(), 1)
        # calling again (duplicate webhook / re-confirm) must NOT double-count
        finalize_coupon_redemption(order)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)
        self.assertEqual(CouponRedemption.objects.filter(coupon=self.coupon).count(), 1)

    def test_abandoned_order_does_not_burn_coupon(self):
        # An unpaid (never-finalized) order records no redemption, so the one-time
        # coupon is still available to the customer.
        from .models import CouponRedemption
        from .services import quote_for_order
        req = self._req()
        quote_for_order(req, 100)   # place_order path, no payment
        self.assertEqual(CouponRedemption.objects.count(), 0)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 0)
