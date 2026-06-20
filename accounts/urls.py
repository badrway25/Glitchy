from django.urls import path
from . import views


urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('', views.dashboard, name='dashboard'),

    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('forgotPassword/', views.forgotPassword, name='forgotPassword'),
    path('resetpassword_validate/<uidb64>/<token>/', views.resetpassword_validate, name='resetpassword_validate'),
    path('resetPassword/', views.resetPassword, name='resetPassword'),

    path('orders/', views.my_orders, name='my_orders'),
    path('orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('transactions/', views.transactions, name='transactions'),

    path("addresses/", views.address_list, name="address_list"),
    path("addresses/new/", views.address_create, name="address_create"),
    path("addresses/<int:address_id>/edit/", views.address_edit, name="address_edit"),
    path("addresses/<int:address_id>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:address_id>/default/", views.address_set_default, name="address_set_default"),

]