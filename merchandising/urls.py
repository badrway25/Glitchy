from django.urls import path

from . import views

app_name = "merchandising"

urlpatterns = [
    path("collections/", views.collections_index, name="collections"),
    path("collections/<slug:slug>/", views.collection_detail, name="collection"),
    path("style-quiz/", views.style_quiz, name="style_quiz"),
    path("notify-me/", views.notify_me, name="notify_me"),
    path("outfit/add/", views.outfit_add, name="outfit_add"),
]
