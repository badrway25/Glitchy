"""F4 guard: the PDP variant dropdown must layer above the CTA row and the mobile
sticky CTA, but below the size guide, the lightbox and the modals.

The PDP colour/size control is `.custom-select-dd .dropdown-menu` (NOT `.pmsel`,
which drives the store filters and the checkout country field). It already sat above
the CTA, but at z-index 1400 it also sat ABOVE the size guide — the spec wants the
size guide on top. Both dropdown implementations now share one layer token so the
ordering can't silently regress:
    sticky CTA (1080) < variant dropdown < size guide (1220) < toasts (1400) < modal (2000)
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

CSS = (Path(__file__).resolve().parent.parent / "greatkart" / "static" / "css"
       / "premium.css").read_text(encoding="utf-8")


def _z(selector_fragment):
    m = re.search(re.escape(selector_fragment) + r"[^{}]*\{[^}]*?z-index:\s*(\d+)",
                  CSS)
    return int(m.group(1)) if m else None


def _token(name):
    m = re.search(re.escape(name) + r"\s*:\s*(\d+)", CSS)
    return int(m.group(1)) if m else None


class PdpDropdownLayerTests(SimpleTestCase):
    def test_shared_variant_dropdown_layer_defined(self):
        layer = _token("--z-variant-dropdown")
        self.assertIsNotNone(layer, "variant dropdown layer token missing")
        self.assertEqual(layer, 1150)

    def test_both_dropdown_implementations_use_the_token(self):
        # PDP colour/size and the filter/checkout selects reference one layer.
        self.assertIn("--z-variant-dropdown", CSS)
        pdp = re.search(r"\.custom-select-dd \.dropdown-menu\{[^}]*z-index:"
                        r"var\(--z-variant-dropdown", CSS)
        pmsel = re.search(r"\.pmsel\.is-open\{z-index:var\(--z-variant-dropdown",
                          CSS)
        self.assertTrue(pdp, "PDP variant dropdown must use the layer token")
        self.assertTrue(pmsel, "pmsel open dropdown must use the layer token")

    def test_layer_sits_above_sticky_cta_and_below_the_overlays(self):
        layer = _token("--z-variant-dropdown")
        sticky = _z(".pdp-sticky-cta")
        size_guide = _z(".sg-modal")
        atc = _z(".atc-backdrop")
        lightbox = _z(".vg-backdrop")
        self.assertTrue(sticky < layer < size_guide,
                        f"want {sticky} < {layer} < {size_guide}")
        self.assertTrue(layer < atc and layer < lightbox)
