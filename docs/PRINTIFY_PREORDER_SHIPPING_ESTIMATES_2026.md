# Pre-order Shipping Estimates (Printify) — 2026

**Status:** implemented on branch `feature/printify-preorder-shipping-estimates`.
Gives the customer an estimated **cost + delivery time before checkout**, using
Printify where possible and honest fallbacks elsewhere. **It never creates a
Printify order**; the real order is only sent after checkout/payment.

---

## 1. What the customer sees

On the **cart** and **checkout** pages a "Estimate delivery / Stima consegna /
Estimer la livraison" card lets the customer enter a destination (country +
postal code) and shows:

- shipping **cost** per available method (Standard / Priority / Express / Economy),
- estimated **delivery window** in business days, and projected from–to dates,
- **product subtotal + shipping = estimated total**,
- an honest **source badge** — "Estimated by Printify" (live) or "Estimated"
  (cached/fallback),
- a disclaimer: final shipping may vary after address validation; delivery is an
  estimate, not a guarantee.

On checkout the widget binds to the billing **country/postal** fields (no
duplicate inputs) and re-estimates when they change.

---

## 2. Printify documentation verified

Endpoint used (read-only — **does not create an order**):

```
POST /v1/shops/{shop_id}/orders/shipping.json
```

**Request** (`printify_integration/printify_client.calculate_order_shipping`):

```json
{
  "line_items": [
    { "product_id": "<shop product id>", "variant_id": 17887, "quantity": 1 }
  ],
  "address_to": { "country": "IT", "region": "", "address1": "", "city": "", "zip": "20100" }
}
```

`line_items` also accept `blueprint_id` + `print_provider_id` + `variant_id` (for
catalog items not yet a shop product) or `sku`. **Response** is a flat map of
**integer cents** per method:

```json
{ "standard": 1000, "express": 5000, "priority": 3000, "economy": 399, "printify_express": 800 }
```

> ⚠️ The endpoint returns **cost only — not transit time**. Delivery time is
> therefore always *production (handling) + transit*, where transit is a
> documented per-method estimate (see §4). This is the central honesty point of
> the feature.

Shipping methods are provider-dependent: a provider may return only `standard`,
or add `priority` / `express` / `economy` / `printify_express`.

---

## 3. Architecture (three honest tiers)

`printify_integration/shipping_estimator.estimate_for_cart(...)` resolves the
best source available and records the provenance in `result.source`:

| Tier | `source` | Cost from | Delivery from | When |
|------|----------|-----------|---------------|------|
| 1 | `live_printify` | live `orders/shipping.json` (cents) | production + per-method transit | `SHIPPING_USE_PRINTIFY=True` **and** every cart line resolves to a Printify product/variant |
| 2 | `cached_profile` | persisted `PrintifyShippingProfile` (catalog rate) | profile handling + transit | a catalog profile exists for the blueprint/provider/country |
| 3 | `local_fallback` | `settings.SHIPPING_FALLBACK_RATES` | production + transit | nothing better is available |
| — | `unavailable` | — | — | empty cart or a country we do not advertise |

Each tier degrades to the next on any error (HTTP 400 invalid address, 401/403
auth, 429 rate limit, 5xx, network). Errors are recorded as **safe codes** in
`result.errors_safe` (e.g. `address_invalid`, `rate_limited`) — never a token,
address, or raw payload.

Supporting pieces:

- **`PrintifyShippingEstimateCache`** — short-TTL cache
  (`SHIPPING_ESTIMATE_CACHE_TTL_MINUTES`, default 180) keyed by cart composition
  + **country + postal PREFIX** + method. Stores only the per-method cost map.
  **No PII** (no full postal code, name, email, address).
- **API**: `POST /cart/shipping-estimate/` (`carts.views.shipping_estimate`) —
  CSRF-protected, POST-only, soft per-session throttle, reads the cart
  **server-side**, never trusts a client price, returns JSON, never creates an
  order.
- **Audit**: `python manage.py printify_shipping_estimate_audit` (see §6).
- **Admin**: read-only `PrintifyShippingEstimateCache` list with a "purge
  expired" action.

---

## 4. Delivery-time model (honest, configurable)

```
delivery_days = production_days + transit_days   (business days, weekends skipped)
```

- **production_days** — Printify handling time when known (catalog profile), else
  `settings.SHIPPING_PRODUCTION_DAYS` (default **2–7** business days, Printify's
  published print-on-demand guidance).
- **transit_days** — `settings.SHIPPING_METHOD_TRANSIT_DAYS` per method
  (documented estimates, **not** from the API):

  | method | transit (business days) |
  |--------|-------------------------|
  | economy | 10–30 |
  | standard | 5–20 |
  | priority | 4–12 |
  | express / printify_express | 2–5 |

Projected dates use `add_business_days(today, n)` (weekends excluded). Example:
product €30 + standard shipping €10 → estimated total €40, delivery
*production 2–7 + transit 5–20 = 7–27 business days*.

All of the above is configurable via environment/settings, so the ranges can be
tightened once real provider/lane data is observed.

---

## 5. Countries

- The storefront advertises a curated list (`shipping/constants.COUNTRIES`):
  IT, FR, DE, ES, NL, BE, AT, PT, IE, CH, GB, US, CA, AU.
- The estimator quotes **only** those countries (honest: we don't quote a
  destination we never list). A country outside the list returns
  `available=false` with `country_unsupported`.
- Core EU markets **BE / IT / FR** are covered by the curated list and, where
  catalog profiles are synced, use `cached_profile` rates.
- If `SHIPPING_SUPPORTED_COUNTRIES` is set in the environment, it overrides the
  curated list.

---

## 6. Operations

```bash
# Audit estimates per country (safe output, no order push)
python manage.py printify_shipping_estimate_audit --country IT --country FR --country BE
python manage.py printify_shipping_estimate_audit --product-id 6 --json
python manage.py printify_shipping_estimate_audit --live      # read live rates (needs SHIPPING_USE_PRINTIFY-capable token)
python manage.py printify_shipping_estimate_audit --no-live   # force fallback

# Keep catalog profiles fresh (feeds tier 2)
python manage.py printify_sync_shipping_profiles --apply --country IT --country FR --country BE
```

`--live` flips `SHIPPING_USE_PRINTIFY` **for that process only**; it reads the
read-only shipping endpoint and never writes settings or creates an order.

---

## 7. What is real vs estimated

| Data | Source | Confidence |
|------|--------|------------|
| Shipping cost (live mode) | Printify `orders/shipping.json` | **High** — real, address-specific, in cents |
| Shipping cost (cached) | Printify catalog profile (synced) | Medium — generic per region, not address-specific |
| Shipping cost (fallback) | local settings table | Low — flat estimate |
| Production time | Printify handling time (cached) or 2–7 days | Medium |
| Transit time | documented per-method ranges | **Estimate** — not from the API |
| Delivery dates | computed business days | Estimate — never guaranteed |

---

## 8. Limits / what is missing for production

- **Live mode is OFF by default** (`SHIPPING_USE_PRINTIFY=False`). Costs come
  from cached profiles / fallback until it is enabled in a controlled env.
- **Printify key not rotated** — the live path stays gated behind the rotation
  gate before go-live (see the readiness audit).
- **Transit times are estimates** (the API does not return them). Tighten the
  per-method ranges with observed data per provider/lane.
- **Variant proxy**: cost is computed per blueprint/provider/region (effectively
  flat across variants), so the default variant is used when the exact one is not
  stored on the cart line — acceptable for an estimate.
- **No carrier-level rates / duties / taxes at destination** — only the Printify
  shipping fee is shown; customs/duties are out of scope.
- Catalog profile coverage depends on running `printify_sync_shipping_profiles`
  per country.

---

## 9. Security

- No order is ever created (only the read-only shipping endpoint is called).
- `PRINTIFY_PUSH_ENABLED` stays `False`; no real orders, no real payments.
- No token, PII, or raw API payload is logged, cached, or sent to the client.
- The estimate endpoint is CSRF-protected, POST-only, throttled, and computes
  cost **server-side** (client prices are ignored).
