from django.contrib import admin

from .models import Coupon, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "is_active", "min_order_amount",
                    "used_count", "usage_limit", "valid_to")
    list_filter = ("is_active", "discount_type")
    search_fields = ("code", "description")
    readonly_fields = ("used_count", "created_at")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "amount", "order", "created_at")
    list_filter = ("coupon", "created_at")
    search_fields = ("coupon__code", "user__email")
    readonly_fields = ("coupon", "user", "session_key", "order", "amount", "created_at")

    def has_add_permission(self, request):
        return False
