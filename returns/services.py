"""
Returns / refunds business logic — the 14-day window and refund maths.

Kept free of view/request concerns so it can be unit-tested directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def return_window_days() -> int:
    return int(getattr(settings, "RETURN_WINDOW_DAYS", 14))


@dataclass
class Eligibility:
    eligible: bool
    days_left: int
    deadline: object  # datetime
    reason: str = ""


def eligibility_for_order(order, *, now=None) -> Eligibility:
    """
    An order is returnable if it is a confirmed order and the return window
    (default 14 days) from the order date has not elapsed.
    """
    now = now or timezone.now()
    window = return_window_days()

    if not getattr(order, "is_ordered", False):
        return Eligibility(False, 0, None, reason="not_confirmed")

    placed = getattr(order, "created_at", None)
    if placed is None:
        return Eligibility(False, 0, None, reason="no_date")

    deadline = placed + timedelta(days=window)
    days_left = (deadline.date() - now.date()).days
    if now <= deadline:
        return Eligibility(True, max(days_left, 0), deadline)
    return Eligibility(False, 0, deadline, reason="window_passed")


def is_within_window(order, *, now=None) -> bool:
    return eligibility_for_order(order, now=now).eligible


def default_refund_amount(order) -> float:
    """
    Default proposed refund = items subtotal (goods value). Shipping is usually
    non-refundable for change-of-mind returns under EU rules, but admins can edit.
    """
    subtotal = getattr(order, "items_subtotal", 0) or 0
    if not subtotal:
        # Derive from order lines if subtotal wasn't snapshotted.
        try:
            subtotal = sum(op.line_total() for op in order.orderproduct_set.all())
        except Exception:
            subtotal = max(float(order.order_total) - float(order.tax), 0)
    return round(float(subtotal), 2)
