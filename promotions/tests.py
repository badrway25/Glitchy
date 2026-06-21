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
