"""
Django settings for the greatkart premium fashion store.

All secrets are loaded from environment variables (see .env / .env.example).
Nothing sensitive is hard-coded in this file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a local .env file (never committed).
load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------------------------------- #
# Small env helpers
# --------------------------------------------------------------------------- #
def env(key, default=""):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key, default=None):
    raw = os.environ.get(key)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(key, default=0):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-via-env",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])

# Brand identity (used across templates and emails)
SITE_NAME = env("SITE_NAME", "Glitchy")
SITE_TAGLINE = env("SITE_TAGLINE", "Premium fashion, printed on demand")
SITE_BASE_URL = env("SITE_BASE_URL", "http://127.0.0.1:8000")


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local apps
    "category",
    "accounts",
    "store",
    "carts",
    "orders",
    "printify_integration",
    "shipping",
    "returns",
    "notifications",
    # Third party
    "stripe",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware must sit after SessionMiddleware and before CommonMiddleware
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "greatkart.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "category.context_processors.menu_links",
                "carts.context_processors.counter",
                "shipping.context_processors.shipping_context",
                "greatkart.context_processors.site_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "greatkart.wsgi.application"
ASGI_APPLICATION = "greatkart.asgi.application"
AUTH_USER_MODEL = "accounts.Account"


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------- #
# Password validation
# --------------------------------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------- #
# Internationalization — EN / IT / FR
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

from django.utils.translation import gettext_lazy as _  # noqa: E402

LANGUAGES = [
    ("en", _("English")),
    ("it", _("Italiano")),
    ("fr", _("Français")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]


# --------------------------------------------------------------------------- #
# Static & media
# --------------------------------------------------------------------------- #
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_DIRS = [
    BASE_DIR / "greatkart" / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# --------------------------------------------------------------------------- #
# Auth redirects
# --------------------------------------------------------------------------- #
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {
    messages.ERROR: "danger",
}


# --------------------------------------------------------------------------- #
# Email (SMTP is a FALLBACK; the primary channel is n8n — see notifications app)
# --------------------------------------------------------------------------- #
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@example.com")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", EMAIL_HOST_USER or "support@example.com")
ADMIN_NOTIFY_EMAIL = env("ADMIN_NOTIFY_EMAIL", EMAIL_HOST_USER or "")


# --------------------------------------------------------------------------- #
# Printify
# --------------------------------------------------------------------------- #
PRINTIFY_API_TOKEN = env("PRINTIFY_API_TOKEN", "")
PRINTIFY_SHOP_ID = env("PRINTIFY_SHOP_ID", "")
PRINTIFY_BLUEPRINT_CATEGORY_MAP = {
    145: "t-shirt",
    706: "t-shirt",
}
PRINTIFY_SYNC_OVERWRITE_CATEGORY = False


# --------------------------------------------------------------------------- #
# Stripe
# --------------------------------------------------------------------------- #
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CURRENCY = env("STRIPE_CURRENCY", "eur")

# Payment processing fee model (used for net-margin estimation)
PAYMENT_FEE_PERCENT = float(env("PAYMENT_FEE_PERCENT", "1.5"))   # %
PAYMENT_FEE_FIXED = float(env("PAYMENT_FEE_FIXED", "0.25"))      # currency units


# --------------------------------------------------------------------------- #
# Store economics
# --------------------------------------------------------------------------- #
STORE_TAX_RATE = float(env("STORE_TAX_RATE", "2.0"))            # % applied at checkout
STORE_CURRENCY = env("STORE_CURRENCY", "EUR")
STORE_CURRENCY_SYMBOL = env("STORE_CURRENCY_SYMBOL", "€")


# --------------------------------------------------------------------------- #
# Shipping (fallback configuration used when Printify rates are unavailable)
# --------------------------------------------------------------------------- #
SHIPPING_DEFAULT_COUNTRY = env("SHIPPING_DEFAULT_COUNTRY", "IT")
SHIPPING_FREE_THRESHOLD = float(env("SHIPPING_FREE_THRESHOLD", "80"))
# Fallback rate table: ISO2 -> {first_item, additional_item, min_days, max_days}
SHIPPING_FALLBACK_RATES = {
    "IT": {"first": 4.90, "additional": 1.90, "min_days": 3, "max_days": 6},
    "FR": {"first": 6.90, "additional": 2.40, "min_days": 4, "max_days": 8},
    "DE": {"first": 6.90, "additional": 2.40, "min_days": 4, "max_days": 8},
    "ES": {"first": 6.90, "additional": 2.40, "min_days": 4, "max_days": 8},
    "GB": {"first": 8.90, "additional": 2.90, "min_days": 5, "max_days": 10},
    "US": {"first": 9.90, "additional": 3.40, "min_days": 6, "max_days": 12},
}
SHIPPING_DEFAULT_RATE = {"first": 11.90, "additional": 3.90, "min_days": 7, "max_days": 15}
# Countries we ship to (empty => ship anywhere with default rate)
SHIPPING_SUPPORTED_COUNTRIES = env_list("SHIPPING_SUPPORTED_COUNTRIES", [])
# Use live Printify shipping profiles when available (else fallback table)
SHIPPING_USE_PRINTIFY = env_bool("SHIPPING_USE_PRINTIFY", False)
# Opt-in external IP→country lookup (off by default to keep requests fast/offline)
SHIPPING_GEOIP_API = env_bool("SHIPPING_GEOIP_API", False)


# --------------------------------------------------------------------------- #
# Returns / refunds
# --------------------------------------------------------------------------- #
RETURN_WINDOW_DAYS = env_int("RETURN_WINDOW_DAYS", 14)


# --------------------------------------------------------------------------- #
# n8n automation / email orchestration
# --------------------------------------------------------------------------- #
N8N_ENABLED = env_bool("N8N_ENABLED", False)
N8N_WEBHOOK_BASE_URL = env("N8N_WEBHOOK_BASE_URL", "")
N8N_SHARED_SECRET = env("N8N_SHARED_SECRET", "")
N8N_TIMEOUT = env_int("N8N_TIMEOUT", 15)
N8N_MAX_RETRIES = env_int("N8N_MAX_RETRIES", 3)
# When SMTP should be used as a fallback if an n8n dispatch fails
EMAIL_SMTP_FALLBACK = env_bool("EMAIL_SMTP_FALLBACK", True)


# --------------------------------------------------------------------------- #
# Production-only hardening (auto-enabled when DEBUG is off)
# --------------------------------------------------------------------------- #
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
