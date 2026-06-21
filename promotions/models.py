"""Real coupon engine: percentage or fixed-amount codes with validity window,
minimum order, total usage limit and redemption tracking."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Coupon(models.Model):
    PERCENT = "percent"
    FIXED = "fixed"
    TYPE_CHOICES = [(PERCENT, _("Percentage")), (FIXED, _("Fixed amount"))]

    code = models.CharField(max_length=32, unique=True)
    description = models.CharField(max_length=160, blank=True, default="")
    discount_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=PERCENT)
    value = models.DecimalField(max_digits=8, decimal_places=2,
                                help_text=_("Percent (e.g. 10) or fixed amount (e.g. 5.00)."))

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    usage_limit = models.PositiveIntegerField(default=0, help_text=_("0 = unlimited total redemptions."))
    per_user_limit = models.PositiveIntegerField(
        default=0, help_text=_("0 = unlimited per customer. 1 = one-time per user/guest."))
    used_count = models.PositiveIntegerField(default=0, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

    def validate(self, subtotal, request=None):
        """Return (ok: bool, reason_key: str). reason_key maps to a UI message.
        When `request` is given, also enforces the per-user/guest redemption limit."""
        now = timezone.now()
        if not self.is_active:
            return False, "inactive"
        if self.valid_from and now < self.valid_from:
            return False, "not_started"
        if self.valid_to and now > self.valid_to:
            return False, "expired"
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "used_up"
        if request is not None and self.per_user_limit and self.redemptions_by(request) >= self.per_user_limit:
            return False, "already_used"
        if self.min_order_amount and Decimal(str(subtotal)) < self.min_order_amount:
            return False, "min_order"
        return True, "ok"

    def redemptions_by(self, request):
        """How many times the current user (or guest session) has redeemed this coupon."""
        qs = self.redemptions.all()
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            return qs.filter(user=request.user).count()
        sk = request.session.session_key if getattr(request, "session", None) else None
        return qs.filter(session_key=sk).count() if sk else 0

    def discount_for(self, subtotal):
        sub = Decimal(str(subtotal))
        if self.discount_type == self.PERCENT:
            disc = (sub * self.value / Decimal("100"))
        else:
            disc = self.value
        disc = max(Decimal("0"), min(disc, sub))   # never exceed the subtotal
        return disc.quantize(Decimal("0.01"))


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True)
    session_key = models.CharField(max_length=64, blank=True, default="")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Coupon redemption")
        verbose_name_plural = _("Coupon redemptions")
