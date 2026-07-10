"""Premium add-to-cart confirmation modal — markup, wiring and a11y guards.

The modal is a server-rendered skeleton on the PDP filled by JS from the
enriched add_cart AJAX payload. These tests pin the contract: markup present
(outside the form), a11y attributes, i18n labels, JS wiring literals, and the
toast fallback still in place for pages without the modal.
"""
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from category.models import Category
from store.models import Product, Variation

BASE = Path(__file__).resolve().parent.parent


def _pdp_html(client, lang="en"):
    cat, _ = Category.objects.get_or_create(category_name="T-Shirts", slug="t-shirts")
    p, _created = Product.objects.get_or_create(
        product_name="Modal Tee", slug="modal-tee",
        defaults=dict(price=25, stock=5, category=cat))
    Variation.objects.get_or_create(product=p, variation_category="color",
                                    variation_value="Black")
    with translation.override(lang):
        return client.get(p.get_url()).content.decode()


class ModalMarkupTests(TestCase):
    def test_modal_present_with_a11y_attributes(self):
        html = _pdp_html(self.client)
        self.assertIn('id="atcModal"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn("data-atc-thumb", html)
        self.assertIn("data-atc-close", html)
        self.assertIn("Continue shopping", html)
        self.assertIn("View cart", html)
        self.assertIn("Added to cart", html)
        self.assertIn("Image reflects your selected colour", html)
        self.assertIn('href="%s"' % reverse("cart"), html)

    def test_modal_lives_outside_the_pdp_form(self):
        src = (BASE / "templates" / "store" / "product_detail.html").read_text(
            encoding="utf-8")
        self.assertIn('id="atcModal"', src)
        # the closing </section> of the PDP layout comes before the modal block —
        # i.e. the modal is a sibling of the form, never nested inside #pdpForm
        self.assertLess(src.index("</section>"), src.index('id="atcModal"'))

    def test_modal_js_loaded_globally(self):
        html = _pdp_html(self.client)
        self.assertIn("js/add-cart-modal.js", html)

    def test_italian_labels(self):
        html = _pdp_html(self.client, lang="it")
        self.assertIn("Aggiunto al carrello", html)
        self.assertIn("Continua lo shopping", html)


class ModalJsContractTests(TestCase):
    """File-content guards, in the repo's established style."""

    def _read(self, name):
        return (BASE / "greatkart" / "static" / "js" / name).read_text(encoding="utf-8")

    def test_modal_js_has_trap_and_event_wiring(self):
        js = self._read("add-cart-modal.js")
        for literal in ("focusables", 'e.key === "Tab"', "lastTrigger",
                        "glitchy:cart-added", "preventDefault", 'e.key === "Escape"',
                        "isOpen()"):
            self.assertIn(literal, js, literal)

    def test_store_features_dispatches_and_keeps_toast_fallback(self):
        js = self._read("store-features.js")
        self.assertIn("glitchy:cart-added", js)
        self.assertIn("glToast", js)
        self.assertIn('select.closest(".pmsel")', js)   # pinned by shipping tests

    def test_backdrop_hidden_rule_present(self):
        css = (BASE / "greatkart" / "static" / "css" / "premium.css").read_text(
            encoding="utf-8")
        self.assertIn(".atc-backdrop[hidden]{display:none;}", css)
        self.assertIn(".atc-backdrop{position:fixed;inset:0;z-index:2000;", css)
