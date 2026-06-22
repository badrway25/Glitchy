"""Canonical event names exchanged between Django and n8n."""

# Outbound (Django -> n8n)
ORDER_CREATED = "order.created"
ORDER_PAID = "order.paid"
ORDER_IN_PRODUCTION = "order.in_production"
ORDER_SHIPPED = "order.shipped"
ORDER_TRACKING = "order.tracking_available"
RETURN_REQUESTED = "return.requested"
RETURN_APPROVED = "return.approved"
RETURN_REJECTED = "return.rejected"
REFUND_COMPLETED = "refund.completed"
CART_ABANDONED = "cart.abandoned"
PRINTIFY_ERROR = "printify.error"
MARGIN_NEGATIVE = "margin.negative"
NEWSLETTER_SUBSCRIBED = "newsletter.subscribed"
SUPPORT_AUTOREPLY = "support.autoreply"
SUPPORT_ORDER_HELP = "support.order_help"
STYLE_QUIZ_COMPLETED = "style_quiz_completed"
PRODUCT_NOTIFICATION_SIGNUP = "product_notification_signup"
OUTFIT_ADD_TO_CART = "outfit_add_to_cart"
WISHLIST_REMINDER = "wishlist_reminder"
CART_SAVED_FOR_LATER = "cart_saved_for_later"
HIGH_INTENT_USER = "high_intent_user"
INTERNAL_ALERT = "internal.alert"

# Each event maps to an n8n webhook path segment + a human label.
EVENT_CATALOG = {
    ORDER_CREATED: "Order confirmation email",
    ORDER_PAID: "Payment received email",
    ORDER_IN_PRODUCTION: "Order in production email",
    ORDER_SHIPPED: "Order shipped email",
    ORDER_TRACKING: "Tracking available email",
    RETURN_REQUESTED: "Return request received email",
    RETURN_APPROVED: "Return approved email",
    RETURN_REJECTED: "Return rejected email",
    REFUND_COMPLETED: "Refund completed email",
    CART_ABANDONED: "Abandoned cart recovery email",
    PRINTIFY_ERROR: "Internal: Printify error alert",
    MARGIN_NEGATIVE: "Internal: negative margin alert",
    NEWSLETTER_SUBSCRIBED: "Newsletter welcome email",
    SUPPORT_AUTOREPLY: "Support auto-reply email",
    SUPPORT_ORDER_HELP: "Order help request from account",
    STYLE_QUIZ_COMPLETED: "Style quiz completed (growth)",
    PRODUCT_NOTIFICATION_SIGNUP: "Notify-me sign-up (growth)",
    OUTFIT_ADD_TO_CART: "Outfit added to cart (growth)",
    WISHLIST_REMINDER: "Wishlist reminder (growth)",
    CART_SAVED_FOR_LATER: "Saved-for-later reminder (growth)",
    HIGH_INTENT_USER: "High-intent user signal (growth)",
    INTERNAL_ALERT: "Internal: generic ops alert",
}

ALL_EVENTS = list(EVENT_CATALOG.keys())
EVENT_CHOICES = [(name, name) for name in ALL_EVENTS]
