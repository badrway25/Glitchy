"""One production-safe Printify sync tick (run every ~30s by a systemd timer).

LIGHT by design: re-syncs a tiny batch of stale products (read-only GET + local
upsert), capped request budget, DB lock (no overlap), persisted backoff on 429/5xx.
NEVER creates orders, NEVER publishes products. OFF unless PRINTIFY_SYNC_ENABLED.

    # safe dry run (default): report what WOULD sync, no network
    python manage.py printify_sync_daemon_tick

    # production (what the systemd timer runs): execute against the live API
    python manage.py printify_sync_daemon_tick --apply --live --safe-output

    # manual one-off ignoring the enabled gate (still needs --apply --live to write)
    python manage.py printify_sync_daemon_tick --force --apply --live
"""
import json

from django.core.management.base import BaseCommand

from printify_integration.sync_daemon import run_tick


class Command(BaseCommand):
    help = "Run one light, production-safe Printify sync tick (no orders, no publish)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually re-sync (else pure dry-run report).")
        parser.add_argument("--live", action="store_true",
                            help="Call the real Printify API (else no network).")
        parser.add_argument("--force", action="store_true",
                            help="Ignore PRINTIFY_SYNC_ENABLED (manual one-off).")
        parser.add_argument("--max-products", type=int, default=None,
                            help="Override batch size for this run.")
        parser.add_argument("--max-requests", type=int, default=None,
                            help="Override request budget for this run.")
        parser.add_argument("--safe-output", action="store_true",
                            help="Emit compact JSON only (for timers/logs).")
        parser.add_argument("--json", action="store_true", help="Emit the result as JSON.")

    def handle(self, *args, **opts):
        result = run_tick(
            apply=opts["apply"], live=opts["live"], force=opts["force"],
            batch_size=opts["max_products"], max_requests=opts["max_requests"],
        ).as_dict()

        if opts["safe_output"] or opts["json"]:
            self.stdout.write(json.dumps(result, separators=(",", ":")))
            return

        style = self.style.SUCCESS if result["ok"] else self.style.ERROR
        self.stdout.write(style(
            f"tick: action={result['action']} reason={result['reason']} "
            f"enabled={result['enabled']} live={result['live']} apply={result['apply']}"))
        self.stdout.write(
            f"  stale={result['stale_total']} selected={result['selected']} "
            f"synced={result['synced']} errors={result['errors']} "
            f"requests={result['requests_used']} backoff={result['backoff_active']}")
        for m in result["messages"]:
            self.stdout.write(f"  - {m}")
