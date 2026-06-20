from django.urls import path
from . import views

urlpatterns = [
    path('place_order/', views.place_order, name='place_order'),
    path('payments/', views.payments, name='payments'),
    path('order_complete/', views.order_complete, name='order_complete'),
    path("invoice/<str:order_number>/pdf/", views.invoice_pdf, name="invoice_pdf"),

    path("stripe/create-intent/", views.stripe_create_intent, name="stripe_create_intent"),
    path("stripe/confirm/", views.stripe_confirm, name="stripe_confirm"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("stripe/return/", views.stripe_return, name="stripe_return"),


]