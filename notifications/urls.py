from django.urls import path

from . import api, views

urlpatterns = [
    # n8n -> Django (HMAC-protected)
    path("api/n8n/incoming-email/", api.incoming_email, name="n8n_incoming_email"),
    path("api/n8n/support-message/", api.support_message, name="n8n_support_message"),
    path("api/n8n/email-status/", api.email_status, name="n8n_email_status"),
    path("api/n8n/order-event/", api.order_event, name="n8n_order_event"),
    # Public newsletter opt-in (site form)
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
]
