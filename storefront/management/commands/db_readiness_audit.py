"""Safe, read-only audit of the current database for transfer/readiness checks.

Prints aggregate COUNTS and migration state only — NO PII, NO secrets, NO row
contents. The database name is masked. Use it to compare source vs server before
and after a controlled transfer (see docs/DB_TRANSFER_TO_SERVER_2026.md).

    python manage.py db_readiness_audit
    python manage.py db_readiness_audit --json --safe-output
"""
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def _mask(name: str) -> str:
    """Mask a db name/path with a FIXED pattern (no length/content leak)."""
    if not name:
        return "—"
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    if len(base) <= 2:
        return "***"
    return f"{base[0]}***{base[-1]}"


def _safe_call(fn):
    """Run a count callable, returning None on any error (e.g. unmigrated DB)."""
    try:
        return fn()
    except Exception:
        return None


def _count(label_app_model):
    """Safe count: returns None if the model/app is absent."""
    app_label, model_name = label_app_model
    try:
        model = apps.get_model(app_label, model_name)
        return model.objects.count()
    except Exception:
        return None


class Command(BaseCommand):
    help = "Read-only DB readiness audit (counts + migrations, no PII, masked db name)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--safe-output", action="store_true")

    def handle(self, *args, **opts):
        engine = connection.settings_dict.get("ENGINE", "")
        db_name = connection.settings_dict.get("NAME", "")

        # migration state (applied vs pending) without touching data
        executor = MigrationExecutor(connection)
        applied = len(executor.loader.applied_migrations)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = [f"{mig.app_label}.{mig.name}" for mig, _backwards in plan]

        counts = {
            "products": _count(("store", "Product")),
            "categories": _count(("category", "Category")),
            "users": _safe_call(lambda: get_user_model().objects.count()),
            "orders": _count(("orders", "Order")),
            "order_products": _count(("orders", "OrderProduct")),
            "printify_products": self._printify_products(),
            "printify_shipping_profiles": _count(("printify_integration", "PrintifyShippingProfile")),
            "product_translations": _count(("store", "ProductDescriptionTranslation")),
        }
        printify_breakdown = self._printify_breakdown()

        report = {
            "engine": engine.rsplit(".", 1)[-1],
            "database_masked": _mask(db_name),
            "migrations_applied": applied,
            "migrations_pending": len(pending),
            "migrations_pending_names": pending,
            "counts": counts,
            "printify_sync_breakdown": printify_breakdown,
            "pii_included": False,
        }

        if opts["json"] or opts["safe_output"]:
            self.stdout.write(json.dumps(report, separators=(",", ":")))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("Database readiness audit (no PII)"))
        self.stdout.write(f"  engine            {report['engine']}")
        self.stdout.write(f"  database          {report['database_masked']} (masked)")
        self.stdout.write(f"  migrations        {applied} applied, {len(pending)} pending")
        for name in pending:
            self.stdout.write(f"                    - pending: {name}")
        self.stdout.write("  counts:")
        for k, v in counts.items():
            self.stdout.write(f"    {k:28s} {'—' if v is None else v}")
        self.stdout.write("  printify sync breakdown:")
        for k, v in printify_breakdown.items():
            self.stdout.write(f"    {k:28s} {v}")
        self.stdout.write(self.style.WARNING(
            "\nCounts only — no row contents, no PII, db name masked. Safe to paste in a report."))

    def _printify_products(self):
        try:
            Product = apps.get_model("store", "Product")
            return Product.objects.exclude(printify_product_id__isnull=True).exclude(
                printify_product_id="").count()
        except Exception:
            return None

    def _printify_breakdown(self):
        out = {}
        try:
            Product = apps.get_model("store", "Product")
            for status in ("synced", "not_synced", "updated", "error"):
                out[status] = Product.objects.filter(printify_sync_status=status).count()
        except Exception:
            pass
        return out
