from django.urls import path
from . import views

urlpatterns = [
    path('place_order/', views.place_order, name='place_order'),
    path('payments/', views.payments, name='payments'),
    path('order_complete/', views.order_complete, name='order_complete'),
    path("invoice/<str:order_number>/pdf/", views.invoice_pdf, name="invoice_pdf"),

    path("paypal/create-order/", views.paypal_create_order, name="paypal_create_order"),
    path("paypal/capture/", views.paypal_capture, name="paypal_capture"),
    path("paypal/status/", views.paypal_status, name="paypal_status"),
    path("status/", views.order_status, name="order_status"),
    path("stripe/create-intent/", views.stripe_create_intent, name="stripe_create_intent"),
    path("stripe/confirm/", views.stripe_confirm, name="stripe_confirm"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("stripe/return/", views.stripe_return, name="stripe_return"),


]