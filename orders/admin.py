from django.contrib import admin, messages
from .models import Payment, Order, OrderProduct
from .services import push_order_to_printify


@admin.action(description="Accept order and send to Printify")
def accept_and_send(modeladmin, request, queryset):
    for order in queryset:
        order.status = "Accepted"
        order.save(update_fields=["status"])

        try:
            push_order_to_printify(order, auto_send=True)
            messages.success(request, f"Sent {order.order_number} to Printify.")
        except Exception as e:
            messages.error(request, f"Printify error for {order.order_number}: {e}")


class OrderProductInline(admin.TabularInline):
    model = OrderProduct
    readonly_fields = ("payment", "user", "product", "quantity", "product_price", "ordered")
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "email", "status", "is_ordered", "created_at", "printify_order_id", "printify_status")
    list_filter = ("status", "is_ordered")
    search_fields = ("order_number", "first_name", "last_name", "email", "phone")
    inlines = [OrderProductInline]
    actions = [accept_and_send]


admin.site.register(Payment)
admin.site.register(OrderProduct)
