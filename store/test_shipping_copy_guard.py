"""Shipping/returns copy coherence guards (ultra-premium polish phase).

Two invariants:
1. NO invented delivery/return claims in templates — every time/cost promise must come from
   config (SHIPPING_FALLBACK_RATES / RETURN_WINDOW_DAYS / FREE_SHIPPING_THRESHOLD) or be
   phrased as "calculated at checkout". Hardcoded promises like "30-day returns" or
   "2–4 business days" broke coherence before this phase — this test keeps them out.
2. ONE delivery-time model funnel-wide: the cart/checkout estimator local fallback must show
   the same door-to-door days as the PDP quote (the rate table), not a different window.
"""
import pathlib
import re

from django.conf import settings
from django.test import TestCase

TEMPLATES = pathlib.Path(settings.BASE_DIR) / "templates"

# Claim patterns that must never appear hardcoded in storefront templates.
# (config-bound {{ d }}-day / {{ t }} renderings don't match these literals.)
FORBIDDEN = [
    re.compile(r"\b30-day\b", re.I),                       # invented return window
    re.compile(r"\b\d+\s*[–-]\s*\d+\s+business days\b"),   # hardcoded delivery ranges in copy
    re.compile(r"\b24\s?h\b|\b48\s?h\b", re.I),            # invented express promises
    re.compile(r"consegna in \d+ giorni", re.I),
    re.compile(r"livraison en \d+ jours", re.I),
]

# Files allowed to contain digit-ranges because they render CONFIG values around them
# (none currently — keep the list explicit so additions are conscious decisions).
ALLOWED = set()


class ShippingCopyGuardTests(TestCase):
    def test_no_invented_delivery_or_return_claims_in_templates(self):
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            rel = path.relative_to(TEMPLATES).as_posix()
            if rel in ALLOWED or rel.startswith("admin/"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in FORBIDDEN:
                m = pat.search(text)
                if m:
                    offenders.append(f"{rel}: '{m.group(0)}'")
        self.assertEqual(offenders, [], "Invented shipping/return claims found:\n" + "\n".join(offenders))

    def test_trust_claims_render_from_config(self):
        html = self.client.get("/").content.decode()
        # the home hero + trust strip must show the CONFIG values, whatever they are
        self.assertIn(f"{settings.RETURN_WINDOW_DAYS}-day", html)
        self.assertIn(str(int(settings.SHIPPING_FREE_THRESHOLD)), html)

    def test_estimator_fallback_matches_rate_table_days(self):
        """Cart/checkout estimator (local fallback tier) == PDP quote days (rate table)."""
        from types import SimpleNamespace
        from printify_integration.shipping_estimator import estimate_for_cart
        from shipping.services import fallback_quote
        class _EmptyQS:                      # chainable queryset stub -> no variants
            def all(self):
                return []
            def filter(self, **kw):
                return self
            def exclude(self, **kw):
                return self
            def order_by(self, *a):
                return self
            def first(self):
                return None
        item = SimpleNamespace(
            product=SimpleNamespace(price=10.0, printify_product_id="", printify_shop_id="",
                                    printify_blueprint_id=None, printify_print_provider_id=None,
                                    variation_set=_EmptyQS()),
            variations=_EmptyQS(), quantity=1)
        fq = fallback_quote("IT", total_quantity=1, subtotal=10)
        res = estimate_for_cart([item], "IT", subtotal=10, use_cache=False)
        self.assertTrue(res.available)
        self.assertEqual(res.source, "local_fallback")
        self.assertEqual((res.delivery_days_min, res.delivery_days_max),
                         (fq.min_days, fq.max_days),
                         "Estimator fallback must show the same door-to-door days as the PDP quote")
