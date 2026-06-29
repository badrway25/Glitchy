"""URL configuration for the greatkart premium store."""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

from . import views, seo
from store.views import faq as faq_view
from store.admin_views import printify_dashboard

# Non-localized routes: admin, language switch, and machine/API endpoints
# (n8n webhooks must have stable, prefix-free URLs).
urlpatterns = [
    path("admin/printify-dashboard/", printify_dashboard, name="printify_dashboard"),
    path("admin/", admin.site.urls),
    path("sitemap.xml", seo.sitemap_xml, name="sitemap"),
    path("robots.txt", seo.robots_txt, name="robots"),
    path("i18n/", include("django.conf.urls.i18n")),   # set_language endpoint
    path("", include("notifications.urls")),           # /api/n8n/... + newsletter
    path("shipping/", include("shipping.urls")),       # country switcher
    path("assistant/", include("assistant.urls")),     # contextual AI assistant API
    path("storefront/", include("storefront.urls")),   # first-party analytics beacon
    path("wishlist/", include("wishlist.urls")),        # wishlist / save-for-later
    path("coupon/", include("promotions.urls")),        # coupon apply/remove
]

# Localized, user-facing routes. English stays prefix-free; IT/FR get /it/, /fr/.
urlpatterns += i18n_patterns(
    path("", views.home, name="home"),
    path("faq/", faq_view, name="faq"),
    path("privacy/", TemplateView.as_view(template_name="legal/privacy.html",
         extra_context={"legal_title": _("Privacy Policy")}), name="privacy"),
    path("terms/", TemplateView.as_view(template_name="legal/terms.html",
         extra_context={"legal_title": _("Terms of Service")}), name="terms"),
    path("cookies/", TemplateView.as_view(template_name="legal/cookies.html",
         extra_context={"legal_title": _("Cookie Policy")}), name="cookies"),
    path("", include("merchandising.urls")),       # collections, style-quiz, notify-me, outfit
    path("store/", include("store.urls")),
    # Convenience/safety redirect: the real checkout lives at /cart/checkout/.
    # A bookmarked or typed /checkout/ (or a naive smoke check) would 404 otherwise.
    path("checkout/", RedirectView.as_view(pattern_name="checkout", permanent=False),
         name="checkout_redirect"),
    path("cart/", include("carts.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("returns/", include("returns.urls")),
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
