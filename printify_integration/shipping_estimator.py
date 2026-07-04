"""
Pre-order shipping ESTIMATES — cost + delivery time shown BEFORE checkout.

Three honest tiers, best first:

    1. live_printify  — POST /shops/{id}/orders/shipping.json for the real cart
                        + destination. Returns per-method COST (cents). Read-only:
                        NEVER creates or pushes an order.
    2. cached_profile — persisted catalog rates (PrintifyShippingProfile), keyed
                        by (blueprint, provider, country).
    3. local_fallback — the configurable settings rate table (shipping.services).

The Printify API returns shipping COST but NOT transit time, so delivery time is
always production (handling) + transit, where transit is a documented, clearly
labelled ESTIMATE per method. Nothing here is presented as a guarantee.

Security: no token, no PII and no raw provider payload ever leaves this module or
is logged. The short-TTL cache stores only a country code + postal-code prefix.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from dataclasses import asdict, dataclass, field

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from shipping.constants import COUNTRY_NAMES
from shipping.services import fallback_quote, is_country_supported

logger = logging.getLogger("printify")

# Provenance of an estimate (also mirrored on PrintifyShippingEstimateCache).
SOURCE_LIVE = "live_printify"
SOURCE_CACHED = "cached_profile"
SOURCE_LOCAL = "local_fallback"
SOURCE_UNAVAILABLE = "unavailable"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #
def format_days_range(a: int, b: int) -> str:
    """Localized 'A–B business days' (or 'N business days' when equal/single)."""
    if a and b and a != b:
        return _("%(a)d–%(b)d business days") % {"a": a, "b": b}
    return _("%(d)d business days") % {"d": b or a}


@dataclass
class ShippingOption:
    method: str
    label: str
    cost: float
    cost_display: str
    currency: str
    delivery_days_min: int
    delivery_days_max: int
    free: bool = False
    selected: bool = False

    def as_dict(self) -> dict:
        data = asdict(self)
        data["delivery_label"] = format_days_range(self.delivery_days_min, self.delivery_days_max)
        return data


@dataclass
class ShippingEstimateResult:
    available: bool
    source: str                       # live_printify | cached_profile | local_fallback | unavailable
    country: str
    currency: str
    options: list = field(default_factory=list)        # list[ShippingOption]
    selected_method: str = ""
    shipping_cost: float = 0.0
    shipping_cost_display: str = ""
    free: bool = False
    production_days_min: int = 0
    production_days_max: int = 0
    transit_days_min: int = 0
    transit_days_max: int = 0
    delivery_days_min: int = 0
    delivery_days_max: int = 0
    estimated_delivery_from: str = ""  # ISO date
    estimated_delivery_to: str = ""    # ISO date
    disclaimer: str = ""
    mixed_sources: bool = False
    errors_safe: list = field(default_factory=list)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["options"] = [o.as_dict() for o in self.options]
        data["source_label"] = self.source_label
        data["delivery_label"] = self.delivery_label
        return data

    @property
    def source_label(self) -> str:
        if self.source == SOURCE_LIVE:
            return _("Estimated by Printify")
        if self.source in (SOURCE_CACHED,
                           SOURCE_LOCAL):
            return _("Estimated")
        return _("Unavailable")

    @property
    def delivery_label(self) -> str:
        if not self.available:
            return ""
        return format_days_range(self.delivery_days_min, self.delivery_days_max)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _currency() -> str:
    return getattr(settings, "STORE_CURRENCY", "EUR")


def _symbol() -> str:
    return getattr(settings, "STORE_CURRENCY_SYMBOL", "€")


def _money(value: float) -> str:
    if not value:
        return _("Free")
    return f"{_symbol()} {value:,.2f}"


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value):
    """Parse to int, or None when the value is missing/unparseable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def estimate_country_supported(country: str) -> bool:
    """Whether we offer a pre-order estimate for this destination.

    If SHIPPING_SUPPORTED_COUNTRIES is configured, defer to it. Otherwise (the
    "ship anywhere" default) we only quote the countries we actually advertise
    in the storefront dropdown — quoting a country we never list would be
    dishonest, so it returns an explicit "unavailable" instead.
    """
    configured = getattr(settings, "SHIPPING_SUPPORTED_COUNTRIES", []) or []
    if configured:
        return is_country_supported(country)
    return (country or "").upper() in COUNTRY_NAMES


def _postal_prefix(postal_code: str) -> str:
    """Coarse, privacy-preserving postal bucket (first 3 alnum chars)."""
    cleaned = "".join(c for c in (postal_code or "") if c.isalnum()).upper()
    return cleaned[:3]


def add_business_days(start: datetime.date, days: int) -> datetime.date:
    """Add `days` business days (Mon–Fri) to a date, skipping weekends."""
    if days <= 0:
        return start
    d = start
    added = 0
    while added < days:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:  # 0–4 = Mon–Fri
            added += 1
    return d


def methods_in_order() -> list:
    return list(getattr(settings, "SHIPPING_ESTIMATE_METHODS",
                        ["standard", "priority", "express", "economy"]))


# Translation markers: method labels are looked up dynamically from settings,
# which makemessages cannot see — list the literals here so they get extracted.
_METHOD_LABEL_MARKERS = (
    _("Standard"), _("Priority"), _("Express"), _("Economy"), _("Printify Express"),
)


def _method_label(method: str) -> str:
    labels = getattr(settings, "SHIPPING_METHOD_LABELS", {})
    return _(labels.get(method, method.replace("_", " ").title()))


def _production_window() -> tuple:
    pmin, pmax = getattr(settings, "SHIPPING_PRODUCTION_DAYS", (2, 7))
    return int(pmin), int(pmax)


def _transit_window(method: str) -> tuple:
    table = getattr(settings, "SHIPPING_METHOD_TRANSIT_DAYS", {})
    tmin, tmax = table.get(method, (5, 20))
    return int(tmin), int(tmax)


# --------------------------------------------------------------------------- #
# Cart → Printify line items
# --------------------------------------------------------------------------- #
def _resolve_variant_id(cart_item):
    """Best-effort Printify variant id for a cart line.

    Shipping cost is computed per blueprint/provider/region and is effectively
    flat across variants, so the product's default variant is an acceptable
    proxy for an ESTIMATE when the exact variant was not stored on the line.
    """
    vid = getattr(cart_item, "printify_variant_id", None)
    if vid:
        return _int_or_none(vid)
    for v in cart_item.variations.all():
        if getattr(v, "printify_variant_id", None):
            got = _int_or_none(v.printify_variant_id)
            if got:
                return got
    product = cart_item.product
    var = (product.variation_set.filter(printify_variant_id__isnull=False)
           .exclude(printify_variant_id="")
           .order_by("-printify_is_default", "id").first())
    if var:
        return _int_or_none(var.printify_variant_id)
    return None


def build_line_items(cart_items):
    """Build Printify line_items for the order-shipping endpoint.

    Returns (line_items, live_capable, total_qty). `live_capable` is True only
    when EVERY line resolves to a Printify product/variant (the endpoint needs
    the whole order to produce an accurate total).
    """
    line_items = []
    total_qty = 0
    live_capable = True
    for it in cart_items or []:
        qty = max(1, _safe_int(getattr(it, "quantity", 1), 1))
        total_qty += qty
        product = getattr(it, "product", None)
        variant_id = _resolve_variant_id(it) if product else None
        if product is None or variant_id is None:
            live_capable = False
            continue
        if product.printify_product_id:
            line_items.append({"product_id": str(product.printify_product_id),
                               "variant_id": variant_id, "quantity": qty})
        elif product.printify_blueprint_id and product.printify_provider_id:
            line_items.append({"blueprint_id": int(product.printify_blueprint_id),
                               "print_provider_id": int(product.printify_provider_id),
                               "variant_id": variant_id, "quantity": qty})
        else:
            live_capable = False
    if not line_items:
        live_capable = False
    return line_items, live_capable, (total_qty or 1)


def _cart_signature(cart_items, country, postal_code, method, free) -> str:
    parts = []
    for it in cart_items or []:
        product = getattr(it, "product", None)
        pid = getattr(product, "id", "?")
        qty = _safe_int(getattr(it, "quantity", 1), 1)
        parts.append(f"{pid}x{qty}")
    raw = "|".join(sorted(parts))
    key = f"{raw}|{(country or '').upper()}|{_postal_prefix(postal_code)}|{method}|free={int(bool(free))}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Time model (production + transit → delivery window + dates)
# --------------------------------------------------------------------------- #
def _delivery_window(method: str, handling_min=None, handling_max=None) -> dict:
    pmin, pmax = _production_window()
    if handling_min:
        pmin = int(handling_min)
    if handling_max:
        pmax = int(handling_max)
    if pmax < pmin:
        pmin, pmax = pmax, pmin
    tmin, tmax = _transit_window(method)
    dmin, dmax = pmin + tmin, pmax + tmax
    today = timezone.localdate()
    return {
        "production_days_min": pmin, "production_days_max": pmax,
        "transit_days_min": tmin, "transit_days_max": tmax,
        "delivery_days_min": dmin, "delivery_days_max": dmax,
        "estimated_delivery_from": add_business_days(today, dmin).isoformat(),
        "estimated_delivery_to": add_business_days(today, dmax).isoformat(),
    }


def _window_from_profile(handling: int, min_delivery: int, max_delivery: int) -> dict:
    """Delivery window from a catalog profile's OWN delivery range (no double-count).

    production = handling; transit = the remainder up to the profile's delivery
    range. Falls back to production + the generic transit map if the profile has
    no usable delivery range.
    """
    pmin, pmax = _production_window()
    handling = handling or pmin
    if not (min_delivery and max_delivery and max_delivery >= handling):
        return _delivery_window("standard", handling, handling)
    tmin = max(0, min_delivery - handling)
    tmax = max(0, max_delivery - handling)
    today = timezone.localdate()
    return {
        "production_days_min": handling, "production_days_max": handling,
        "transit_days_min": tmin, "transit_days_max": tmax,
        "delivery_days_min": min_delivery, "delivery_days_max": max_delivery,
        "estimated_delivery_from": add_business_days(today, min_delivery).isoformat(),
        "estimated_delivery_to": add_business_days(today, max_delivery).isoformat(),
    }


def _disclaimer(source: str, mixed: bool) -> str:
    base = _("Final shipping may vary slightly after address validation.")
    if mixed:
        return _("Some items use estimated shipping data.") + " " + base
    if source == SOURCE_LIVE:
        return base
    return _("Estimated delivery — not guaranteed.") + " " + base


# --------------------------------------------------------------------------- #
# Tier 1 — live Printify order-shipping
# --------------------------------------------------------------------------- #
def _live_cost_map(cart_items, country, postal_code, region, city):
    """Call POST /orders/shipping.json. Returns (cost_map_cents, error_code).

    cost_map_cents: {"standard": 1000, ...} in cents, or None on any failure.
    error_code: a short, SAFE token ("address_invalid", "rate_limited", ...).
    """
    if not getattr(settings, "SHIPPING_USE_PRINTIFY", False):
        return None, "disabled"
    line_items, live_capable, _qty = build_line_items(cart_items)
    if not live_capable:
        return None, "not_live_capable"

    address_to = {
        "country": (country or "").upper(),
        "region": region or "",
        "address1": "",          # unknown pre-checkout; cost is driven by country+zip
        "city": city or "",
        "zip": postal_code or "",
    }
    try:
        from .printify_client import get_client
        data = get_client().calculate_order_shipping(line_items, address_to)
    except Exception as exc:  # noqa: BLE001 — degrade to fallback on ANY problem
        status = getattr(exc, "status", None)
        code = {400: "address_invalid", 401: "auth", 403: "auth",
                429: "rate_limited"}.get(status, "unavailable")
        logger.warning("Live shipping estimate failed (%s) → %s", type(exc).__name__, code)
        return None, code

    if not isinstance(data, dict):
        return None, "bad_response"
    known = {"standard", "express", "priority", "economy", "printify_express"}
    cost_map = {}
    for k, v in data.items():
        if k not in known:
            continue
        cents = _int_or_none(v)
        if cents is not None:
            cost_map[k] = cents
    if not cost_map:
        return None, "no_methods"
    return cost_map, ""


# --------------------------------------------------------------------------- #
# Tier 2 — cached catalog profile
# --------------------------------------------------------------------------- #
def _cached_profile_cost(cart_items, country, total_qty):
    """Cost + delivery window from PrintifyShippingProfile rows (catalog data).

    Returns a dict {cost, handling, min_delivery, max_delivery} or None. The
    delivery range is the profile's OWN catalog estimate (not the generic transit
    map), so the cached tier stays consistent with the rest of the storefront.
    """
    from .models import PrintifyShippingProfile
    country = (country or "").upper()
    first_product = None
    for it in cart_items or []:
        p = getattr(it, "product", None)
        if p and p.printify_blueprint_id and p.printify_provider_id:
            first_product = p
            break
    if first_product is None:
        return None

    prof = (PrintifyShippingProfile.objects
            .filter(blueprint_id=first_product.printify_blueprint_id,
                    print_provider_id=first_product.printify_provider_id,
                    country_code=country).first())
    if prof is None:
        prof = (PrintifyShippingProfile.objects
                .filter(blueprint_id=first_product.printify_blueprint_id,
                        print_provider_id=first_product.printify_provider_id,
                        country_code="REST_OF_THE_WORLD").first())
    if prof is None:
        return None
    cost = float(prof.first_item_cost) + float(prof.additional_item_cost) * max(0, total_qty - 1)
    return {"cost": round(cost, 2), "handling": int(prof.handling_days or 0),
            "min_delivery": int(prof.min_delivery_days or 0),
            "max_delivery": int(prof.max_delivery_days or 0)}


# --------------------------------------------------------------------------- #
# Option assembly
# --------------------------------------------------------------------------- #
def _options_from_live(cost_map_cents, free, selected_method):
    options = []
    available = [m for m in methods_in_order() if m in cost_map_cents]
    # Always surface any method Printify returned, even if not in our preferred order.
    for m in cost_map_cents:
        if m not in available:
            available.append(m)
    if selected_method not in available and available:
        selected_method = available[0]
    for m in available:
        win = _delivery_window(m)
        cost = 0.0 if free else round(cost_map_cents[m] / 100.0, 2)
        options.append(ShippingOption(
            method=m, label=_method_label(m), cost=cost, cost_display=_money(cost),
            currency=_currency(), delivery_days_min=win["delivery_days_min"],
            delivery_days_max=win["delivery_days_max"], free=bool(free),
            selected=(m == selected_method)))
    return options, selected_method


def _single_option(method, cost, free, handling_min=None, handling_max=None, days_override=None):
    """days_override=(min,max): use the rate-table door-to-door business days verbatim
    (the same numbers the PDP quote and the order snapshot show) instead of the generic
    production+transit model — one delivery-time model funnel-wide."""
    if days_override and days_override[1]:
        dmin, dmax = int(days_override[0]), int(days_override[1])
        if dmax < dmin:
            dmin, dmax = dmax, dmin
        today = timezone.localdate()
        win = {
            "production_days_min": 0, "production_days_max": 0,
            "transit_days_min": dmin, "transit_days_max": dmax,
            "delivery_days_min": dmin, "delivery_days_max": dmax,
            "estimated_delivery_from": add_business_days(today, dmin).isoformat(),
            "estimated_delivery_to": add_business_days(today, dmax).isoformat(),
        }
    else:
        win = _delivery_window(method, handling_min, handling_max)
    c = 0.0 if free else round(float(cost), 2)
    return ShippingOption(
        method=method, label=_method_label(method), cost=c, cost_display=_money(c),
        currency=_currency(), delivery_days_min=win["delivery_days_min"],
        delivery_days_max=win["delivery_days_max"], free=bool(free), selected=True), win


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def estimate_for_cart(cart_items, country, *, postal_code="", region="", city="",
                      shipping_method="", subtotal=None, use_cache=True):
    """Return a ShippingEstimateResult for the cart + destination.

    Tries live Printify → cached profile → local fallback, degrading gracefully
    and recording the provenance in `source`. Never creates an order.
    """
    cart_items = list(cart_items or [])
    country = (country or getattr(settings, "SHIPPING_DEFAULT_COUNTRY", "IT")).upper()
    currency = _currency()
    errors = []

    # Empty cart → nothing to estimate.
    if not cart_items:
        return ShippingEstimateResult(
            available=False, source=SOURCE_UNAVAILABLE,
            country=country, currency=currency,
            disclaimer=_("Add an item to estimate delivery."),
            errors_safe=["empty_cart"])

    # Unsupported destination → honest, explicit unavailability.
    if not estimate_country_supported(country):
        return ShippingEstimateResult(
            available=False, source=SOURCE_UNAVAILABLE,
            country=country, currency=currency,
            disclaimer=_("We do not ship to this country yet."),
            errors_safe=["country_unsupported"])

    # Subtotal & free-shipping policy (store absorbs shipping over the threshold).
    if subtotal is None:
        subtotal = sum(float(getattr(getattr(it, "product", None), "price", 0) or 0)
                       * _safe_int(getattr(it, "quantity", 1), 1) for it in cart_items)
    threshold = float(getattr(settings, "SHIPPING_FREE_THRESHOLD", 0) or 0)
    free = bool(threshold and subtotal >= threshold)

    methods = methods_in_order()
    selected = shipping_method if shipping_method in methods else (methods[0] if methods else "standard")

    # Cache lookup (skips the network on repeated identical estimates).
    cache_key = _cart_signature(cart_items, country, postal_code, selected, free)
    if use_cache:
        cached = _read_cache(cache_key, country, postal_code, selected)
        if cached is not None:
            return cached

    _line_items, live_capable, total_qty = build_line_items(cart_items)
    mixed = bool(live_capable) and any(
        not (getattr(it, "product", None) and (
            it.product.printify_product_id or
            (it.product.printify_blueprint_id and it.product.printify_provider_id)))
        for it in cart_items)

    # ---- Tier 1: live Printify -------------------------------------------- #
    cost_map, err = _live_cost_map(cart_items, country, postal_code, region, city)
    if cost_map:
        options, selected = _options_from_live(cost_map, free, selected)
        result = _finalise(options, selected, SOURCE_LIVE,
                           country, currency, free, mixed, errors)
        if use_cache:
            _write_cache(cache_key, country, postal_code, result)
        return result
    if err and err not in ("disabled", "not_live_capable", "no_methods"):
        errors.append(err)

    # ---- Tier 2: cached catalog profile ----------------------------------- #
    prof = _cached_profile_cost(cart_items, country, total_qty)
    if prof is not None:
        win = _window_from_profile(prof["handling"], prof["min_delivery"], prof["max_delivery"])
        cost = 0.0 if free else prof["cost"]
        opt = ShippingOption(
            method=selected, label=_method_label(selected), cost=cost,
            cost_display=_money(cost), currency=currency,
            delivery_days_min=win["delivery_days_min"], delivery_days_max=win["delivery_days_max"],
            free=bool(free), selected=True)
        result = _finalise([opt], selected, SOURCE_CACHED,
                           country, currency, free, mixed, errors, win=win)
        if use_cache:
            _write_cache(cache_key, country, postal_code, result)
        return result

    # ---- Tier 3: local settings fallback ---------------------------------- #
    fq = fallback_quote(country, total_quantity=total_qty, subtotal=subtotal)
    if not fq.available:
        return ShippingEstimateResult(
            available=False, source=SOURCE_UNAVAILABLE,
            country=country, currency=currency, disclaimer=fq.message,
            errors_safe=errors + ["country_unsupported"])
    opt, win = _single_option(selected, fq.cost, fq.free or free,
                              days_override=(fq.min_days, fq.max_days))
    result = _finalise([opt], selected, SOURCE_LOCAL,
                       country, currency, fq.free or free, mixed, errors, win=win)
    if use_cache:
        _write_cache(cache_key, country, postal_code, result)
    return result


def _finalise(options, selected_method, source, country, currency, free, mixed, errors, win=None):
    chosen = next((o for o in options if o.method == selected_method), options[0] if options else None)
    # Use the window the selected option was actually built with (it may carry a
    # cached-profile handling time), so the header range matches the option.
    if win is None:
        win = _delivery_window(selected_method)
    today = timezone.localdate()
    result = ShippingEstimateResult(
        available=True, source=source, country=country, currency=currency,
        options=options, selected_method=selected_method,
        shipping_cost=chosen.cost if chosen else 0.0,
        shipping_cost_display=chosen.cost_display if chosen else _money(0),
        free=bool(free),
        production_days_min=win["production_days_min"], production_days_max=win["production_days_max"],
        transit_days_min=win["transit_days_min"], transit_days_max=win["transit_days_max"],
        delivery_days_min=win["delivery_days_min"], delivery_days_max=win["delivery_days_max"],
        estimated_delivery_from=add_business_days(today, win["delivery_days_min"]).isoformat(),
        estimated_delivery_to=add_business_days(today, win["delivery_days_max"]).isoformat(),
        disclaimer=_disclaimer(source, mixed), mixed_sources=mixed, errors_safe=errors)
    return result


# --------------------------------------------------------------------------- #
# Cache I/O (short TTL; no PII)
# --------------------------------------------------------------------------- #
def _read_cache(cache_key, country, postal_code, method):
    try:
        from .models import PrintifyShippingEstimateCache
        row = (PrintifyShippingEstimateCache.objects
               .filter(cart_hash=cache_key, country_code=country,
                       postal_prefix=_postal_prefix(postal_code), shipping_method=method)
               .order_by("-created_at").first())
        if row is None or not row.is_fresh:
            return None
        win_method = method
        cost = float(row.shipping_cost)
        opt = ShippingOption(
            method=win_method, label=_method_label(win_method), cost=cost,
            cost_display=_money(cost), currency=row.currency,
            delivery_days_min=row.delivery_days_min, delivery_days_max=row.delivery_days_max,
            free=(cost == 0.0), selected=True)
        return ShippingEstimateResult(
            available=True, source=row.source, country=row.country_code, currency=row.currency,
            options=[opt], selected_method=win_method, shipping_cost=cost,
            shipping_cost_display=_money(cost), free=(cost == 0.0),
            production_days_min=row.production_days_min, production_days_max=row.production_days_max,
            transit_days_min=row.transit_days_min, transit_days_max=row.transit_days_max,
            delivery_days_min=row.delivery_days_min, delivery_days_max=row.delivery_days_max,
            estimated_delivery_from=add_business_days(timezone.localdate(), row.delivery_days_min).isoformat(),
            estimated_delivery_to=add_business_days(timezone.localdate(), row.delivery_days_max).isoformat(),
            disclaimer=_disclaimer(row.source, False))
    except Exception:  # noqa: BLE001 — cache is best-effort
        return None


def _write_cache(cache_key, country, postal_code, result: ShippingEstimateResult):
    try:
        from .models import PrintifyShippingEstimateCache
        ttl = int(getattr(settings, "SHIPPING_ESTIMATE_CACHE_TTL_MINUTES", 180))
        expires = timezone.now() + datetime.timedelta(minutes=ttl)
        safe_costs = {o.method: round(o.cost, 2) for o in result.options}
        PrintifyShippingEstimateCache.objects.create(
            cart_hash=cache_key, country_code=country,
            postal_prefix=_postal_prefix(postal_code), shipping_method=result.selected_method,
            source=result.source, currency=result.currency, shipping_cost=result.shipping_cost,
            production_days_min=result.production_days_min, production_days_max=result.production_days_max,
            transit_days_min=result.transit_days_min, transit_days_max=result.transit_days_max,
            delivery_days_min=result.delivery_days_min, delivery_days_max=result.delivery_days_max,
            raw_response_safe=safe_costs, expires_at=expires)
    except Exception:  # noqa: BLE001 — never let caching break an estimate
        pass
