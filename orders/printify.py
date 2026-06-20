"""
Thin order-side wrappers around the resilient Printify client.

Kept as functions so existing imports (`from .printify import create_order,
send_to_production`) keep working, but now backed by retry/backoff + rate-limit
handling from printify_integration.printify_client.
"""
from printify_integration.printify_client import get_client


def create_order(payload: dict) -> dict:
    return get_client().create_order(payload)


def send_to_production(printify_order_id: str) -> dict:
    return get_client().send_to_production(printify_order_id)


def get_order(printify_order_id: str) -> dict:
    return get_client().get_order(printify_order_id)
