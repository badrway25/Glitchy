"""Safe monitoring snapshot of the Printify sync daemon (no token, no PII).

    python manage.py printify_sync_status              # human-readable
    python manage.py printify_sync_status --json --safe-output
"""
import json

from django.core.management.base import BaseCommand

from printify_integration.sync_daemon import status_snapshot


class Command(BaseCommand):
    help = "Show Printify sync daemon status (last sync, stale count, backoff). No secrets."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--safe-output", action="store_true",
                            help="Compact JSON only (no token is ever printed regardless).")

    def handle(self, *args, **opts):
        snap = status_snapshot()
        if opts["json"] or opts["safe_output"]:
            self.stdout.write(json.dumps(snap, separators=(",", ":")))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("Printify sync daemon status"))
        rows = [
            ("enabled", snap["enabled"]),
            ("push_enabled (separate)", snap["push_enabled"]),
            ("token present", snap["token_present"]),
            ("interval / batch / max-req", f'{snap["interval_seconds"]}s / '
                                           f'{snap["batch_size"]} / {snap["max_requests_per_tick"]}'),
            ("stale products", snap["stale_products"]),
            ("products synced (total)", snap["products_synced_total"]),
            ("last tick", snap["last_tick_at"] or "never"),
            ("last tick synced/requests", f'{snap["last_tick_synced"]} / {snap["last_tick_requests"]}'),
            ("last full sync", snap["last_full_sync_at"] or "never"),
            ("locked now", snap["locked"]),
            ("backoff active", snap["backoff_active"]),
            ("backoff until", snap["backoff_until"] or "—"),
            ("consecutive errors", snap["consecutive_errors"]),
            ("last error status / at", f'{snap["last_error_status"] or "—"} / '
                                       f'{snap["last_error_at"] or "—"}'),
        ]
        for label, value in rows:
            self.stdout.write(f"  {label:30s} {value}")
