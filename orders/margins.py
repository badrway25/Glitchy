"""
Order margin computation — pure, dependency-light, and unit-testable.

Definitions (all in the order currency):

    revenue_ex_tax   = order_total - tax                 (what we keep, incl. shipping charged)
    total_cost       = cost_production + cost_shipping + payment_fee
    gross_margin     = revenue_ex_tax - cost_production - cost_shipping
    net_margin       = revenue_ex_tax - total_cost
    margin_pct       = net_margin / revenue_ex_tax * 100
    net_after_refund = net_margin - refunded_amount      (refunds erode the margin first)

`band` classifies profitability for admin colour-coding:
    "good"     >= 25%
    "low"      0% .. 25%
    "negative" < 0%
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarginResult:
    currency: str
    revenue_ex_tax: float
    cost_production: float
    cost_shipping: float
    payment_fee: float
    total_cost: float
    gross_margin: float
    net_margin: float
    margin_pct: float
    refunded_amount: float
    net_margin_after_refund: float
    band: str


def _band(margin_pct: float, net_margin: float) -> str:
    if net_margin < 0:
        return "negative"
    if margin_pct >= 25:
        return "good"
    return "low"


def compute_margins_from_values(
    *,
    order_total: float,
    tax: float = 0.0,
    cost_production: float = 0.0,
    cost_shipping: float = 0.0,
    payment_fee: float = 0.0,
    refunded_amount: float = 0.0,
    currency: str = "EUR",
) -> MarginResult:
    order_total = float(order_total or 0)
    tax = float(tax or 0)
    cost_production = float(cost_production or 0)
    cost_shipping = float(cost_shipping or 0)
    payment_fee = float(payment_fee or 0)
    refunded_amount = float(refunded_amount or 0)

    revenue_ex_tax = round(order_total - tax, 2)
    total_cost = round(cost_production + cost_shipping + payment_fee, 2)
    gross_margin = round(revenue_ex_tax - cost_production - cost_shipping, 2)
    net_margin = round(revenue_ex_tax - total_cost, 2)
    margin_pct = round((net_margin / revenue_ex_tax * 100), 1) if revenue_ex_tax > 0 else 0.0
    net_after_refund = round(net_margin - refunded_amount, 2)

    return MarginResult(
        currency=currency,
        revenue_ex_tax=revenue_ex_tax,
        cost_production=round(cost_production, 2),
        cost_shipping=round(cost_shipping, 2),
        payment_fee=round(payment_fee, 2),
        total_cost=total_cost,
        gross_margin=gross_margin,
        net_margin=net_margin,
        margin_pct=margin_pct,
        refunded_amount=round(refunded_amount, 2),
        net_margin_after_refund=net_after_refund,
        band=_band(margin_pct, net_margin),
    )


def compute_margins(order) -> MarginResult:
    """Compute margins for an Order instance."""
    return compute_margins_from_values(
        order_total=getattr(order, "order_total", 0) or 0,
        tax=getattr(order, "tax", 0) or 0,
        cost_production=getattr(order, "cost_production", 0) or 0,
        cost_shipping=getattr(order, "cost_shipping", 0) or 0,
        payment_fee=getattr(order, "payment_fee", 0) or 0,
        refunded_amount=getattr(order, "refunded_amount", 0) or 0,
        currency=getattr(order, "currency", "EUR") or "EUR",
    )


def estimate_payment_fee(amount: float, *, percent: float, fixed: float) -> float:
    """PSP fee = amount * percent% + fixed."""
    return round(float(amount or 0) * float(percent) / 100.0 + float(fixed), 2)
