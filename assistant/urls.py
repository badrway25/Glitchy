from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("suggestions/", views.suggestions, name="suggestions"),
    path("chat/", views.chat, name="chat"),
    path("feedback/", views.feedback, name="feedback"),
    path("support/", views.support_handoff, name="support"),
]
