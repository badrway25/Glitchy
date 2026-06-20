from django.test import RequestFactory, TestCase, override_settings

from shipping.geo import detect_country, set_manual_country, SESSION_KEY
from shipping.services import fallback_quote, is_country_supported


@override_settings(
    SHIPPING_FALLBACK_RATES={
        "IT": {"first": 4.90, "additional": 1.90, "min_days": 3, "max_days": 6},
        "US": {"first": 9.90, "additional": 3.40, "min_days": 6, "max_days": 12},
    },
    SHIPPING_DEFAULT_RATE={"first": 11.90, "additional": 3.90, "min_days": 7, "max_days": 15},
    SHIPPING_FREE_THRESHOLD=80, SHIPPING_DEFAULT_COUNTRY="IT",
    SHIPPING_SUPPORTED_COUNTRIES=[],
)
class FallbackQuoteTests(TestCase):
    def test_single_item_it(self):
        q = fallback_quote("IT", 1, 30)
        self.assertEqual(q.cost, 4.90)
        self.assertTrue(q.available)

    def test_additional_items(self):
        q = fallback_quote("IT", 3, 30)
        self.assertAlmostEqual(q.cost, 4.90 + 1.90 * 2, places=2)

    def test_unknown_country_uses_default_rate(self):
        q = fallback_quote("JP", 1, 10)
        self.assertEqual(q.cost, 11.90)

    def test_free_over_threshold(self):
        q = fallback_quote("US", 1, 100)
        self.assertEqual(q.cost, 0.0)
        self.assertTrue(q.free)

    def test_eta_label(self):
        q = fallback_quote("IT", 1, 10)
        self.assertIn("3", q.eta_label)


@override_settings(SHIPPING_SUPPORTED_COUNTRIES=["IT", "FR"], SHIPPING_DEFAULT_COUNTRY="IT")
class CountrySupportTests(TestCase):
    def test_supported(self):
        self.assertTrue(is_country_supported("IT"))
        self.assertFalse(is_country_supported("US"))

    def test_unsupported_quote_unavailable(self):
        q = fallback_quote("US", 1, 10)
        self.assertFalse(q.available)


class GeoDetectionTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, **meta):
        req = self.rf.get("/", **meta)
        req.session = {}
        return req

    @override_settings(SHIPPING_DEFAULT_COUNTRY="IT")
    def test_default_when_local(self):
        req = self._req(REMOTE_ADDR="127.0.0.1")
        self.assertEqual(detect_country(req), "IT")

    def test_header_country(self):
        req = self._req(HTTP_CF_IPCOUNTRY="FR", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(detect_country(req), "FR")

    def test_manual_session_priority(self):
        req = self._req(HTTP_CF_IPCOUNTRY="FR", REMOTE_ADDR="127.0.0.1")
        set_manual_country(req, "DE")
        self.assertEqual(req.session[SESSION_KEY], "DE")
        self.assertEqual(detect_country(req), "DE")
