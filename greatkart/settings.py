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

# ALLOWED_HOSTS from the environment, so the server never needs a local
# settings.py edit (no dirty working tree). A deploy may export either name in
# /etc/glitchy/env: the bare ALLOWED_HOSTS (what the Glitchy production host uses)
# takes precedence to match the existing server config; DJANGO_ALLOWED_HOSTS is the
# canonical fallback; dev falls back to localhost. Comma-separated; the first one
# set wins, spaces are stripped and empty values ignored. No env value is printed.
def _allowed_hosts():
    return (env_list("ALLOWED_HOSTS")
            or env_list("DJANGO_ALLOWED_HOSTS")
            or ["127.0.0.1", "localhost"])


ALLOWED_HOSTS = _allowed_hosts()

# Canonical site origin (no trailing slash). Used for absolute URLs in sitemap.xml,
# canonical tags, hreflang alternates and og:image. Set to the real domain in prod.
SITE_URL = env("SITE_URL", "http://127.0.0.1:8799").rstrip("/")

# Required for HTTPS POST/CSRF behind a domain (e.g. https://shop.example.com)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])

# Brand identity (used across templates and emails)
SITE_NAME = env("SITE_NAME", "Glitchy")
SITE_TAGLINE = env("SITE_TAGLINE", "Premium fashion, printed on demand")
SITE_BASE_URL = env("SITE_BASE_URL", "http://127.0.0.1:8000")


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
INSTALLED_APPS = [
    # Unfold premium admin — MUST come before django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
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
    "payments",
    "shipping",
    "returns",
    "notifications",
    "assistant",
    "storefront",
    "wishlist",
    "promotions",
    "merchandising",
    # Third party
    "stripe",
]

# --------------------------------------------------------------------------- #
# Unfold premium admin — "Glitchy Commerce Studio" control center.
# Brand: espresso ink + champagne gold (matches the storefront tokens).
# --------------------------------------------------------------------------- #
def _gl_admin_css(request):
    from django.templatetags.static import static
    return static("glitchy_admin/premium.css")


def _gl_admin_forms_css(request):
    from django.templatetags.static import static
    return static("glitchy_admin/forms.css")


def _gl_admin_js(request):
    from django.templatetags.static import static
    return static("glitchy_admin/motion.js")


def _gl_ops_js(request):
    from django.templatetags.static import static
    return static("glitchy_admin/ops-modal.js")


def _gl_ops_css(request):
    from django.templatetags.static import static
    return static("glitchy_admin/ops-modal.css")


# Brand assets (deferred static() so resolution happens at request time, not import time).
def _gl_logo_dark(request):        # dark ink — shown on LIGHT admin background
    from django.templatetags.static import static
    return static("images/brand/logo-glitchy-nav.png")


def _gl_logo_light(request):       # light ink — shown on DARK admin background
    from django.templatetags.static import static
    return static("images/brand/logo-glitchy-nav-light.png")


def _gl_mark(request):
    from django.templatetags.static import static
    return static("images/brand/logo-glitchy-mark.png")


def _gl_favicon(request):
    from django.templatetags.static import static
    return static("images/favicon.ico")


# gettext_lazy for admin i18n — lazy, safe at settings import (no premature translation).
from django.utils.translation import gettext_lazy as _  # noqa: E402 (harvested by makemessages)

UNFOLD = {
    "SITE_TITLE": _("Glitchy Commerce Studio"),
    "SITE_HEADER": _("Glitchy Commerce Studio"),
    "SITE_SUBHEADER": _("Print-on-demand operations"),
    "SITE_URL": "/",
    # Glitchy branding — replaces Unfold's default material-symbols "settings" mark.
    "SITE_LOGO": {"light": _gl_logo_dark, "dark": _gl_logo_light},   # horizontal nav logo
    "SITE_ICON": {"light": _gl_mark, "dark": _gl_mark},              # square monogram mark
    "SITE_SYMBOL": "storefront",                                     # valid Material Symbol fallback only
    "SITE_FAVICONS": [{"rel": "icon", "sizes": "any", "type": "image/x-icon", "href": _gl_favicon}],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "STYLES": [_gl_admin_css, _gl_admin_forms_css, _gl_ops_css],
    "SCRIPTS": [_gl_admin_js, _gl_ops_js],
    "ENVIRONMENT": "greatkart.admin_ext.environment_callback",
    "DASHBOARD_CALLBACK": "greatkart.admin_ext.dashboard_callback",
    "COLORS": {
        "primary": {
            "50": "250 247 240", "100": "243 236 222", "200": "230 214 184",
            "300": "214 187 140", "400": "194 156 96", "500": "166 130 76",
            "600": "140 108 62", "700": "112 86 50", "800": "84 65 40",
            "900": "60 47 30", "950": "34 26 17",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Commerce"),
                "separator": True,
                "items": [
                    {"title": _("Products"), "icon": "inventory_2", "link": "/admin/store/product/"},
                    {"title": _("Categories"), "icon": "category", "link": "/admin/category/category/"},
                    {"title": _("Orders"), "icon": "receipt_long", "link": "/admin/orders/order/"},
                    {"title": _("Customers"), "icon": "group", "link": "/admin/accounts/account/"},
                ],
            },
            {
                "title": _("Printify control"),
                "separator": True,
                "items": [
                    {"title": _("Printify accounts"), "icon": "vpn_key", "link": "/admin/printify_integration/printifyaccountconfig/"},
                    {"title": _("Sync monitor"), "icon": "sync", "link": "/admin/printify_integration/printifysyncstate/"},
                    {"title": _("Sync logs"), "icon": "history", "link": "/admin/printify_integration/synclog/"},
                    {"title": _("Shipping profiles"), "icon": "local_shipping", "link": "/admin/printify_integration/printifyshippingprofile/"},
                ],
            },
            {
                "title": _("Payment control"),
                "separator": True,
                "items": [
                    {"title": _("Payment providers"), "icon": "payments", "link": "/admin/payments/paymentproviderconfig/"},
                    {"title": _("Payment monitor"), "icon": "monitoring", "link": "/admin/payments/paymentevent/"},
                ],
            },
        ],
    },
}

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
                "storefront.context_processors.announcement",
                "wishlist.context_processors.wishlist_globals",
                "accounts.context_processors.portal_counts",
                "greatkart.context_processors.seo_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "greatkart.wsgi.application"
ASGI_APPLICATION = "greatkart.asgi.application"
AUTH_USER_MODEL = "accounts.Account"


# --------------------------------------------------------------------------- #
# Database — SQLite by default; set DATABASE_URL (postgres://...) in production.
# --------------------------------------------------------------------------- #
def _database_from_url(url):
    """Minimal postgres/sqlite DATABASE_URL parser (no extra dependency)."""
    from urllib.parse import urlparse, unquote

    p = urlparse(url)
    if p.scheme in ("postgres", "postgresql", "psql"):
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote((p.path or "/").lstrip("/")),
            "USER": unquote(p.username or ""),
            "PASSWORD": unquote(p.password or ""),
            "HOST": p.hostname or "",
            "PORT": str(p.port or ""),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        }
    if p.scheme == "sqlite":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": p.path or str(BASE_DIR / "db.sqlite3")}
    raise ValueError(f"Unsupported DATABASE_URL scheme: {p.scheme}")


_DATABASE_URL = env("DATABASE_URL", "")
if _DATABASE_URL:
    DATABASES = {"default": _database_from_url(_DATABASE_URL)}
else:
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

# Optional WhiteNoise: serve static via gunicorn without nginx. No-op if not
# installed (staging can simply `pip install whitenoise`).
try:
    import whitenoise  # noqa: F401

    _sec_mw = "django.middleware.security.SecurityMiddleware"
    if _sec_mw in MIDDLEWARE and "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
        MIDDLEWARE.insert(MIDDLEWARE.index(_sec_mw) + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        # WhiteNoise gzip/brotli compression + far-future caching, served straight from
        # gunicorn (no nginx needed). We use the COMPRESSED (non-manifest) backend so a
        # stray url()/source-map ref inside vendored CSS (bootstrap.css.map) can't break
        # collectstatic; cache-busting for our own assets is already handled by ASSET_VERSION.
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
except ImportError:
    pass


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
# Fernet key (from env only, never in the repo) that encrypts an admin-entered Printify token
# at rest. Generate once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# If unset, the admin refuses to save a token (fail-closed); env PRINTIFY_API_TOKEN still works.
PRINTIFY_CONFIG_KEY = env("PRINTIFY_CONFIG_KEY", "")
# Separate Fernet key for admin-entered PAYMENT secrets (Stripe/PayPal). Own blast radius.
PAYMENT_CONFIG_KEY = env("PAYMENT_CONFIG_KEY", "")
# Safety switch: when False, orders are NOT pushed to the real Printify shop
# (used for integration dry-runs so no real Printify order is created).
PRINTIFY_PUSH_ENABLED = env_bool("PRINTIFY_PUSH_ENABLED", True)
PRINTIFY_BLUEPRINT_CATEGORY_MAP = {
    145: "t-shirt",
    706: "t-shirt",
}
PRINTIFY_SYNC_OVERWRITE_CATEGORY = False
# Commercial fallback category (slug of an EXISTING customer-facing category) used when a
# Printify blueprint has no mapping. The sync must NEVER create a technical "Printify" category.
PRINTIFY_DEFAULT_CATEGORY_SLUG = env("PRINTIFY_DEFAULT_CATEGORY_SLUG", "t-shirt")
# Rotation gates: both the OpenAI and Printify credentials were shared in chat (exposed).
# Staging/prod is blocked until the owner revokes each, issues a new one, and flips these.
OPENAI_KEY_ROTATED = env_bool("OPENAI_KEY_ROTATED", False)
PRINTIFY_KEY_ROTATED = env_bool("PRINTIFY_KEY_ROTATED", False)

# --- Production-safe Printify sync daemon (light 30s tick) ------------------- #
# OFF by default everywhere. Enable on the server ONLY via env (PRINTIFY_SYNC_ENABLED=True).
# The tick is deliberately light: a tiny batch of stale products re-synced (read-only
# GET + local upsert) per run, capped request budget, DB lock, persisted backoff on
# 429/5xx. It NEVER creates orders and NEVER publishes products (publishing also stays
# gated behind the separate PRINTIFY_PUSH_ENABLED). Full discovery sync is manual.
PRINTIFY_SYNC_ENABLED = env_bool("PRINTIFY_SYNC_ENABLED", False)
# Informational only (shown in status). The REAL cadence is the systemd .timer
# (OnUnitActiveSec); changing this env var does not change how often the tick runs.
PRINTIFY_SYNC_INTERVAL_SECONDS = env_int("PRINTIFY_SYNC_INTERVAL_SECONDS", 30)
PRINTIFY_SYNC_BATCH_SIZE = env_int("PRINTIFY_SYNC_BATCH_SIZE", 2)
PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK = env_int("PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK", 5)
PRINTIFY_SYNC_BACKOFF_SECONDS = env_int("PRINTIFY_SYNC_BACKOFF_SECONDS", 60)
PRINTIFY_SYNC_STALE_AFTER_MINUTES = env_int("PRINTIFY_SYNC_STALE_AFTER_MINUTES", 360)
PRINTIFY_SYNC_FULL_INTERVAL_MINUTES = env_int("PRINTIFY_SYNC_FULL_INTERVAL_MINUTES", 1440)
PRINTIFY_SYNC_LOCK_TIMEOUT_SECONDS = env_int("PRINTIFY_SYNC_LOCK_TIMEOUT_SECONDS", 120)


# --------------------------------------------------------------------------- #
# Stripe
# --------------------------------------------------------------------------- #
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CURRENCY = env("STRIPE_CURRENCY", "eur")

# PayPal (client id is a PUBLIC identifier, but kept configurable via env)
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = env("PAYPAL_SECRET", "")          # server-side, required to VERIFY a payment
PAYPAL_CURRENCY = env("PAYPAL_CURRENCY", "EUR")
PAYPAL_API_BASE = env("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")
# PayPal stays OFF until server-side capture verification is configured (client id + secret).
# It only flips on when explicitly enabled AND both credentials are present (see orders/paypal.py).
PAYPAL_ENABLED = env_bool("PAYPAL_ENABLED", False) and bool(PAYPAL_CLIENT_ID) and bool(PAYPAL_SECRET)

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
# Social profiles (footer): empty = the button simply doesn't render (no dead links)
SOCIAL_INSTAGRAM = env("SOCIAL_INSTAGRAM", "")
SOCIAL_TIKTOK = env("SOCIAL_TIKTOK", "")
SOCIAL_YOUTUBE = env("SOCIAL_YOUTUBE", "")
SOCIAL_FACEBOOK = env("SOCIAL_FACEBOOK", "")

SHIPPING_DEFAULT_COUNTRY = env("SHIPPING_DEFAULT_COUNTRY", "IT")
SHIPPING_FREE_THRESHOLD = float(env("SHIPPING_FREE_THRESHOLD", "80"))
# Fallback rate table: ISO2 -> {first_item, additional_item, min_days, max_days}
# NOTE: min_days/max_days below are DOOR-TO-DOOR business-day estimates (they already
# include production) — the PDP quote, the cart/checkout estimator fallback and the order
# snapshot all show these same numbers (one delivery-time model funnel-wide).
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
# Pre-order shipping ESTIMATES (cost + delivery time shown BEFORE checkout)
# --------------------------------------------------------------------------- #
# Customer-facing methods, in display order. Each key matches a field returned
# by Printify's order-shipping endpoint (POST .../orders/shipping.json, cents).
SHIPPING_ESTIMATE_METHODS = env_list(
    "SHIPPING_ESTIMATE_METHODS", ["standard", "priority", "express", "economy"])
# Production / handling window (BUSINESS days) used when Printify handling time
# is unknown. Printify's published guidance is ~2–7 business days for print-on-demand.
SHIPPING_PRODUCTION_DAYS = (
    int(env("SHIPPING_PRODUCTION_DAYS_MIN", "2")),
    int(env("SHIPPING_PRODUCTION_DAYS_MAX", "7")),
)
# Transit window (BUSINESS days) per shipping method. The Printify API returns
# shipping COST but NOT transit time, so these are honest, documented estimates
# by method — always labelled "estimated" to the customer (never a guarantee).
SHIPPING_METHOD_TRANSIT_DAYS = {
    "economy":          (10, 30),
    "standard":         (5, 20),
    "priority":         (4, 12),
    "express":          (2, 5),
    "printify_express": (2, 5),
}
# Human label per method (translated at render time via gettext).
SHIPPING_METHOD_LABELS = {
    "economy": "Economy", "standard": "Standard", "priority": "Priority",
    "express": "Express", "printify_express": "Printify Express",
}
# Live-estimate cache TTL (minutes). Live rates can drift, so keep it short.
SHIPPING_ESTIMATE_CACHE_TTL_MINUTES = int(env("SHIPPING_ESTIMATE_CACHE_TTL_MINUTES", "180"))


# --------------------------------------------------------------------------- #
# Returns / refunds
# --------------------------------------------------------------------------- #
RETURN_WINDOW_DAYS = env_int("RETURN_WINDOW_DAYS", 14)


# --------------------------------------------------------------------------- #
# n8n automation / email orchestration
# --------------------------------------------------------------------------- #
N8N_ENABLED = env_bool("N8N_ENABLED", False)
N8N_WEBHOOK_BASE_URL = env("N8N_WEBHOOK_BASE_URL", "")
# Primary enforcement: a static shared header validated by n8n native Header Auth.
N8N_HEADER_AUTH_NAME = env("N8N_HEADER_AUTH_NAME", "X-N8N-AUTH")
N8N_HEADER_AUTH_SECRET = env("N8N_HEADER_AUTH_SECRET", "")
# Optional application-level signature (observability / defense-in-depth).
N8N_SHARED_SECRET = env("N8N_SHARED_SECRET", "")
N8N_TIMEOUT = env_int("N8N_TIMEOUT", 15)
N8N_MAX_RETRIES = env_int("N8N_MAX_RETRIES", 3)
# When SMTP should be used as a fallback if an n8n dispatch fails
EMAIL_SMTP_FALLBACK = env_bool("EMAIL_SMTP_FALLBACK", True)


# --------------------------------------------------------------------------- #
# Contextual AI shopping assistant
# --------------------------------------------------------------------------- #
# The assistant answers ONLY from site context (catalog + curated knowledge).
# With no API key it gracefully falls back to keyword retrieval over the KB.
AI_ASSISTANT_ENABLED = env_bool("AI_ASSISTANT_ENABLED", True)
AI_PROVIDER = env("AI_PROVIDER", "openai")          # openai | mock
AI_MODEL = env("AI_MODEL", "gpt-4o-mini")
AI_API_KEY = env("AI_API_KEY", "")                  # never hardcode; from env only
AI_MAX_TOKENS = env_int("AI_MAX_TOKENS", 500)
AI_TIMEOUT_SECONDS = env_int("AI_TIMEOUT_SECONDS", 20)
AI_RATE_LIMIT = env_int("AI_RATE_LIMIT", 20)        # messages per session per hour
AI_CONTEXT_ONLY = env_bool("AI_CONTEXT_ONLY", True)
AI_MAX_INPUT_CHARS = env_int("AI_MAX_INPUT_CHARS", 600)


# --------------------------------------------------------------------------- #
# Logging — console handler; level from env. Never logs secrets (we log status
# codes + truncated errors only). Stripe/Printify/n8n webhook secrets are never
# written to logs anywhere in the codebase.
# --------------------------------------------------------------------------- #
LOG_LEVEL = env("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "notifications": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "orders": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "printify": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}


# --------------------------------------------------------------------------- #
# Production-only hardening (auto-enabled when DEBUG is off)
# --------------------------------------------------------------------------- #
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
