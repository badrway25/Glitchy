"""Lightweight SEO endpoints: sitemap.xml (with EN/IT/FR hreflang alternates) and
robots.txt. No external dependency on django.contrib.sites — URLs are absolute against
settings.SITE_URL."""
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils import translation


def _abs(path):
    return f"{settings.SITE_URL}{path}"


def _alternates(path):
    """EN (unprefixed) + /it/ + /fr/ variants for an unprefixed path."""
    p = path if path.startswith("/") else "/" + path
    return {
        "en": _abs(p),
        "it": _abs("/it" + p),
        "fr": _abs("/fr" + p),
    }


def _entries():
    """(path, changefreq, priority) for every public, crawlable URL."""
    from store.models import Product
    from category.models import Category
    from merchandising.models import Collection

    items = [("/", "daily", "1.0"), ("/store/", "daily", "0.9"),
             ("/faq/", "monthly", "0.5"), ("/collections/", "weekly", "0.6"),
             ("/style-quiz/", "monthly", "0.4")]
    # In the default (EN) activation so reverse() returns unprefixed paths.
    with translation.override("en"):
        for p in Product.objects.filter(is_available=True):
            items.append((p.get_url(), "weekly", "0.8"))
        for c in Category.objects.all():
            items.append((c.get_url(), "weekly", "0.7"))
        for col in Collection.objects.filter(is_active=True):
            items.append((col.get_url(), "weekly", "0.6"))
    # de-dup, keep order
    seen, out = set(), []
    for path, cf, pr in items:
        if path not in seen:
            seen.add(path)
            out.append((path, cf, pr))
    return out


def sitemap_xml(request):
    rows = []
    for path, changefreq, priority in _entries():
        alts = _alternates(path)
        links = "".join(
            f'<xhtml:link rel="alternate" hreflang="{lang}" href="{href}"/>'
            for lang, href in alts.items())
        links += f'<xhtml:link rel="alternate" hreflang="x-default" href="{alts["en"]}"/>'
        rows.append(
            f"<url><loc>{alts['en']}</loc>{links}"
            f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
           + "".join(rows) + "</urlset>")
    return HttpResponse(xml, content_type="application/xml")


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /cart/",
        "Disallow: /orders/",
        "Disallow: /wishlist/",
        "Disallow: /coupon/",
        "Disallow: /assistant/",
        "Disallow: /storefront/",
        "Disallow: /store/autocomplete/",
        "",
        f"Sitemap: {_abs('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
