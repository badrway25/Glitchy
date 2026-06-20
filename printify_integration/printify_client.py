"""
Resilient Printify API client.

Features:
    * Bearer auth from settings (token never logged).
    * Automatic retry with exponential backoff on 429 / 5xx, honouring Retry-After.
    * Sensible timeouts and a typed error (`PrintifyError`).
    * Catalog (blueprint / variants / providers / shipping), product, and order
      endpoints needed for sync, costing, shipping estimates and fulfilment.
"""
from __future__ import annotations

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger("printify")


class PrintifyError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class PrintifyClient:
    BASE = "https://api.printify.com/v1"

    def __init__(self, token: str | None = None, shop_id=None, *, timeout=30, max_retries=3):
        self.token = token or getattr(settings, "PRINTIFY_API_TOKEN", "")
        self.shop_id = str(shop_id or getattr(settings, "PRINTIFY_SHOP_ID", ""))
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": f"{getattr(settings, 'SITE_NAME', 'greatkart')}/1.0",
        })

    # ------------------------------------------------------------------ #
    # Core request with retry/backoff
    # ------------------------------------------------------------------ #
    def _request(self, method, path, *, params=None, json=None):
        url = f"{self.BASE}{path}"
        backoff = 1.0
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(method, url, params=params, json=json,
                                            timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Printify network error (%s %s) attempt %d: %s",
                               method, path, attempt, type(exc).__name__)
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                logger.warning("Printify %s on %s %s, retrying in %.1fs (attempt %d)",
                               resp.status_code, method, path, wait, attempt)
                if attempt < self.max_retries:
                    time.sleep(wait)
                    backoff *= 2
                    continue
                raise PrintifyError(f"HTTP {resp.status_code} after {attempt} attempts",
                                    status=resp.status_code)

            if resp.status_code >= 400:
                raise PrintifyError(f"HTTP {resp.status_code}: {resp.text[:300]}",
                                    status=resp.status_code)

            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                return {}

        raise PrintifyError(f"Network failure after {self.max_retries} attempts: {last_exc}")

    def _get(self, path, **kw):
        return self._request("GET", path, **kw)

    def _post(self, path, **kw):
        return self._request("POST", path, **kw)

    # ------------------------------------------------------------------ #
    # Shops & products
    # ------------------------------------------------------------------ #
    def get_shops(self):
        return self._get("/shops.json")

    def list_products(self, shop_id=None, limit=50, page=1):
        sid = shop_id or self.shop_id
        return self._get(f"/shops/{sid}/products.json", params={"limit": limit, "page": page})

    def get_product(self, product_id, shop_id=None):
        sid = shop_id or self.shop_id
        return self._get(f"/shops/{sid}/products/{product_id}.json")

    # ------------------------------------------------------------------ #
    # Catalog (blueprint, variants, providers, shipping)
    # ------------------------------------------------------------------ #
    def get_blueprint(self, blueprint_id):
        return self._get(f"/catalog/blueprints/{blueprint_id}.json")

    def get_print_providers(self, blueprint_id):
        return self._get(f"/catalog/blueprints/{blueprint_id}/print_providers.json")

    def get_variants(self, blueprint_id, provider_id):
        return self._get(
            f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json")

    def get_shipping_info(self, blueprint_id, provider_id):
        """Shipping profiles (handling time + cost per region) for a blueprint/provider."""
        return self._get(
            f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json")

    # ------------------------------------------------------------------ #
    # Orders / fulfilment
    # ------------------------------------------------------------------ #
    def create_order(self, payload, shop_id=None):
        sid = shop_id or self.shop_id
        return self._post(f"/shops/{sid}/orders.json", json=payload)

    def send_to_production(self, order_id, shop_id=None):
        sid = shop_id or self.shop_id
        return self._post(f"/shops/{sid}/orders/{order_id}/send_to_production.json", json={})

    def get_order(self, order_id, shop_id=None):
        sid = shop_id or self.shop_id
        return self._get(f"/shops/{sid}/orders/{order_id}.json")

    def list_orders(self, shop_id=None, limit=10, page=1):
        sid = shop_id or self.shop_id
        return self._get(f"/shops/{sid}/orders.json", params={"limit": limit, "page": page})


def get_client() -> PrintifyClient:
    """Factory using project settings."""
    return PrintifyClient(
        token=getattr(settings, "PRINTIFY_API_TOKEN", ""),
        shop_id=getattr(settings, "PRINTIFY_SHOP_ID", ""),
    )
