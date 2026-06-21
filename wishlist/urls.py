from django.urls import path

from . import views

app_name = "wishlist"

urlpatterns = [
    path("toggle/", views.toggle, name="toggle"),
    path("saved/", views.saved_items, name="saved"),
    path("save-for-later/", views.save_for_later, name="save_for_later"),
]
