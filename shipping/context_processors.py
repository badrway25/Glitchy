"""Expose the detected shipping country + selector list to every template."""
from .constants import COUNTRIES, country_name
from .geo import detect_country


def shipping_context(request):
    country = detect_country(request)
    return {
        "ship_country": country,
        "ship_country_name": country_name(country),
        "ship_countries": COUNTRIES,
    }
