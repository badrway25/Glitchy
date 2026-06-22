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


class CouponRaceHardeningTests(TestCase):
    """Phase 21: total per-user enforcement at the authoritative finalize gate."""
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.coupon = Coupon.objects.create(code="ONE", discount_type="percent",
                                            value=Decimal("10"), per_user_limit=1)

    def _user(self, email="u@example.com"):
        u = self.User.objects.create_user(email=email, first_name="U", last_name="U",
                                          username=email.split("@")[0], password="pw12345!")
        u.is_active = True; u.save()
        return u

    def _order(self, user, number, paid=True):
        from orders.models import Order
        return Order.objects.create(user=user, first_name="U", last_name="U", phone="1",
                                    email=user.email, address_line_1="x", city="c", state="s",
                                    country="US", order_total=90, tax=0, ip="127.0.0.1",
                                    order_number=number, coupon_code="ONE", discount=10,
                                    is_ordered=paid)

    def test_two_paid_orders_same_user_redeem_once(self):
        from .models import CouponRedemption
        from .services import finalize_coupon_redemption
        u = self._user()
        a, b = self._order(u, "A1"), self._order(u, "B1")
        finalize_coupon_redemption(a)
        finalize_coupon_redemption(b)   # over per-user limit -> honored, not re-recorded
        self.assertEqual(CouponRedemption.objects.filter(coupon=self.coupon).count(), 1)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)

    def test_duplicate_webhook_same_order_no_double_count(self):
        from .models import CouponRedemption
        from .services import finalize_coupon_redemption
        a = self._order(self._user(), "A2")
        finalize_coupon_redemption(a)
        finalize_coupon_redemption(a)   # duplicate webhook / re-confirm
        self.assertEqual(CouponRedemption.objects.filter(order=a).count(), 1)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)

    def test_global_usage_limit_enforced_at_finalize(self):
        from .models import CouponRedemption
        from .services import finalize_coupon_redemption
        self.coupon.usage_limit = 1; self.coupon.per_user_limit = 0; self.coupon.save()
        a = self._order(self._user("a@x.com"), "A3")
        b = self._order(self._user("b@x.com"), "B3")
        finalize_coupon_redemption(a)
        finalize_coupon_redemption(b)   # global limit reached -> honored, not recorded
        self.assertEqual(CouponRedemption.objects.filter(coupon=self.coupon).count(), 1)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)

    def test_unique_constraint_blocks_second_redemption_per_order(self):
        from django.db import IntegrityError, transaction
        from .models import CouponRedemption
        a = self._order(self._user(), "A4")
        CouponRedemption.objects.create(coupon=self.coupon, order=a, amount=Decimal("10"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CouponRedemption.objects.create(coupon=self.coupon, order=a, amount=Decimal("10"))

    def test_place_order_guard_blocks_second_pending_order(self):
        # User already has a pending (unpaid) order carrying ONE -> can't stash it again.
        from django.contrib.sessions.backends.db import SessionStore
        from .services import quote_for_order
        u = self._user()
        self._order(u, "PEND", paid=False)   # pending order already has coupon_code=ONE
        sess = SessionStore(); sess["coupon_code"] = "ONE"; sess.save()

        class Req:
            user = u
            session = sess
        code, disc = quote_for_order(Req(), 100)
        self.assertEqual(code, "")
        self.assertEqual(disc, Decimal("0"))

    def test_guest_session_one_time_at_finalize(self):
        from orders.models import Order
        from .models import CouponRedemption
        from .services import finalize_coupon_redemption
        o1 = Order.objects.create(first_name="G", last_name="G", phone="1", email="g@x.com",
                                  address_line_1="x", city="c", state="s", country="US",
                                  order_total=90, tax=0, ip="1", order_number="G1",
                                  coupon_code="ONE", discount=10, is_ordered=True,
                                  is_guest=True, session_key="sess-abc")
        o2 = Order.objects.create(first_name="G", last_name="G", phone="1", email="g@x.com",
                                  address_line_1="x", city="c", state="s", country="US",
                                  order_total=90, tax=0, ip="1", order_number="G2",
                                  coupon_code="ONE", discount=10, is_ordered=True,
                                  is_guest=True, session_key="sess-abc")
        finalize_coupon_redemption(o1)
        finalize_coupon_redemption(o2)
        self.assertEqual(CouponRedemption.objects.filter(coupon=self.coupon).count(), 1)
