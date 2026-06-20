import requests
from django.conf import settings

PRINTIFY_BASE = "https://api.printify.com/v1"

def _headers():
    return {
        "Authorization": f"Bearer {settings.PRINTIFY_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "YourStore",
    }

def create_order(payload: dict) -> dict:
    url = f"{PRINTIFY_BASE}/shops/{settings.PRINTIFY_SHOP_ID}/orders.json"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def send_to_production(printify_order_id: str) -> dict:
    url = f"{PRINTIFY_BASE}/shops/{settings.PRINTIFY_SHOP_ID}/orders/{printify_order_id}/send_to_production.json"
    r = requests.post(url, headers=_headers(), json={}, timeout=30)
    r.raise_for_status()
    return r.json()
