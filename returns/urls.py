from django.urls import path

from . import views

app_name = "returns"

urlpatterns = [
    path("", views.returns_policy, name="policy"),
    path("request/<str:order_number>/", views.request_return, name="request"),
    path("status/<uuid:token>/", views.return_status, name="status"),
]
