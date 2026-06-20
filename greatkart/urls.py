"""URL configuration for the greatkart premium store."""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

# Non-localized routes: admin, language switch, and machine/API endpoints
# (n8n webhooks must have stable, prefix-free URLs).
urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),   # set_language endpoint
    path("", include("notifications.urls")),           # /api/n8n/... + newsletter
    path("shipping/", include("shipping.urls")),       # country switcher
]

# Localized, user-facing routes. English stays prefix-free; IT/FR get /it/, /fr/.
urlpatterns += i18n_patterns(
    path("", views.home, name="home"),
    path("store/", include("store.urls")),
    path("cart/", include("carts.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("returns/", include("returns.urls")),
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
