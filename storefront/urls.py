from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("event/", views.track_event, name="event"),
]
