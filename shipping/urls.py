from django.urls import path

from . import views

urlpatterns = [
    path("set-country/", views.set_country, name="set_country"),
]
