"""Phase 59: production-safe Printify sync tick — safety tests.

Verifies the tick is OFF by default, dry-runs without --live, won't overlap (lock),
respects backoff, syncs stale-only within the request budget, enters backoff on 429,
and NEVER creates orders or publishes products. No real network; a fake client is
injected. No token is ever emitted.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from category.models import Category
from printify_integration.models import PrintifySyncState
from printify_integration.printify_client import PrintifyError
from printify_integration.sync_daemon import run_tick, status_snapshot
from store.models import Product


class FakeClient:
    """Records calls; get_product returns a payload (or raises). create_order /
    send_to_production must NEVER be called by the tick."""
    def __init__(self, raise_status=None):
        self.raise_status = raise_status
        self.get_calls = []
        self.orders_created = 0
        self.sent_to_production = 0

    def get_product(self, product_id, shop_id=None):
        self.get_calls.append(product_id)
        if self.raise_status:
            raise PrintifyError(f"HTTP {self.raise_status}", status=self.raise_status)
        return {"id": product_id, "title": "x", "variants": [], "images": [], "options": []}

    def create_order(self, *a, **k):           # pragma: no cover - must not run
        self.orders_created += 1
        raise AssertionError("tick must never create orders")

    def send_to_production(self, *a, **k):       # pragma: no cover - must not run
        self.sent_to_production += 1
        raise AssertionError("tick must never publish/send to production")


SYNC_ON = dict(PRINTIFY_SYNC_ENABLED=True, PRINTIFY_API_TOKEN="test-token-not-real",
               PRINTIFY_SYNC_BATCH_SIZE=2, PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK=5,
               PRINTIFY_SYNC_STALE_AFTER_MINUTES=360, PRINTIFY_SYNC_BACKOFF_SECONDS=60)


class SyncDaemonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(category_name="Tees", slug="tees")

    def _make(self, name, pid, *, status="synced", synced_minutes_ago=10_000):
        synced_at = (timezone.now() - timedelta(minutes=synced_minutes_ago)
                     if synced_minutes_ago is not None else None)
        return Product.objects.create(
            product_name=name, slug=name.lower().replace(" ", "-"), price=20, stock=9999,
            category=self.cat, printify_product_id=pid,
            printify_sync_status=status, printify_synced_at=synced_at)

    # -- gating ---------------------------------------------------------------
    @override_settings(PRINTIFY_SYNC_ENABLED=False)
    def test_disabled_skips(self):
        self._make("A", "pp1")
        res = run_tick()
        self.assertEqual(res.reason, "disabled")
        self.assertEqual(res.synced, 0)

    @override_settings(**SYNC_ON)
    def test_dry_run_without_live(self):
        self._make("A", "pp1")
        client = FakeClient()
        res = run_tick(force=True, apply=True, live=False, client=client)
        self.assertEqual(res.reason, "dry_run")
        self.assertEqual(res.stale_total, 1)
        self.assertEqual(client.get_calls, [])  # no network

    @override_settings(**SYNC_ON)
    def test_lock_prevents_overlap(self):
        self._make("A", "pp1")
        # simulate another tick already holding the lock
        self.assertTrue(PrintifySyncState.try_acquire("other", 120))
        client = FakeClient()
        res = run_tick(force=True, apply=True, live=True, client=client)
        self.assertEqual(res.reason, "locked")
        self.assertEqual(client.get_calls, [])

    @override_settings(**SYNC_ON)
    def test_backoff_skips(self):
        self._make("A", "pp1")
        state = PrintifySyncState.load()
        state.backoff_until = timezone.now() + timedelta(minutes=5)
        state.save()
        client = FakeClient()
        res = run_tick(force=True, apply=True, live=True, client=client)
        self.assertEqual(res.reason, "backoff")
        self.assertTrue(res.backoff_active)
        self.assertEqual(client.get_calls, [])

    # -- live behaviour -------------------------------------------------------
    @override_settings(**SYNC_ON)
    def test_live_syncs_stale_only_and_never_publishes(self):
        stale = self._make("Stale", "pp-stale", status="not_synced", synced_minutes_ago=None)
        fresh = self._make("Fresh", "pp-fresh", status="synced", synced_minutes_ago=1)
        client = FakeClient()
        with mock.patch("printify_integration.services._upsert_product",
                        return_value=(stale, False)) as upsert:
            res = run_tick(force=True, apply=True, live=True, client=client)
        # only the stale product's id was fetched; the fresh one was not
        self.assertIn("pp-stale", client.get_calls)
        self.assertNotIn("pp-fresh", client.get_calls)
        self.assertEqual(res.synced, 1)
        self.assertTrue(upsert.called)
        # NEVER orders / publishes
        self.assertEqual(client.orders_created, 0)
        self.assertEqual(client.sent_to_production, 0)

    @override_settings(**dict(SYNC_ON, PRINTIFY_SYNC_MAX_REQUESTS_PER_TICK=1))
    def test_max_requests_respected(self):
        for i in range(4):
            self._make(f"S{i}", f"pp{i}", status="not_synced", synced_minutes_ago=None)
        client = FakeClient()
        with mock.patch("printify_integration.services._upsert_product",
                        return_value=(None, False)):
            res = run_tick(force=True, apply=True, live=True, client=client)
        self.assertLessEqual(res.requests_used, 1)
        self.assertLessEqual(len(client.get_calls), 1)

    @override_settings(**SYNC_ON)
    def test_429_enters_backoff_and_stops(self):
        self._make("A", "ppa", status="not_synced", synced_minutes_ago=None)
        self._make("B", "ppb", status="not_synced", synced_minutes_ago=None)
        client = FakeClient(raise_status=429)
        res = run_tick(force=True, apply=True, live=True, client=client)
        self.assertEqual(res.reason, "backoff")
        self.assertTrue(res.backoff_active)
        state = PrintifySyncState.load()
        self.assertIsNotNone(state.backoff_until)
        self.assertEqual(state.last_error_status, 429)
        # stopped early after the first 429 (did not hammer the API)
        self.assertEqual(len(client.get_calls), 1)

    @override_settings(**SYNC_ON)
    def test_nothing_stale_is_noop(self):
        self._make("Fresh", "pp-fresh", status="synced", synced_minutes_ago=1)
        client = FakeClient()
        res = run_tick(force=True, apply=True, live=True, client=client)
        self.assertEqual(res.reason, "nothing_stale")
        self.assertEqual(client.get_calls, [])

    # -- safety: lock always released ----------------------------------------
    @override_settings(**SYNC_ON)
    def test_lock_released_after_run(self):
        self._make("Fresh", "pp-fresh", status="synced", synced_minutes_ago=1)
        run_tick(force=True, apply=True, live=True, client=FakeClient())
        # a subsequent acquire must succeed (lock was released)
        self.assertTrue(PrintifySyncState.try_acquire("next", 120))

    # -- safe output (no token) ----------------------------------------------
    @override_settings(**SYNC_ON)
    def test_status_snapshot_has_no_token(self):
        snap = status_snapshot()
        self.assertIn("token_present", snap)
        self.assertTrue(snap["token_present"])           # boolean, not the value
        self.assertNotIn("test-token-not-real", str(snap))
        self.assertFalse(snap["push_enabled"])           # publishing stays off
