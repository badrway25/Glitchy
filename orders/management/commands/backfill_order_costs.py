from django.core.management.base import BaseCommand

from orders.services import backfill_order_costs


class Command(BaseCommand):
    help = ("Estimate costs/margins for historical orders (cost_production==0). "
            "Production cost is backfilled ONLY from real synced Printify data.")

    def add_arguments(self, parser):
        # SAFETY: dry-run is the DEFAULT. Writing requires the explicit --apply flag.
        parser.add_argument("--apply", action="store_true",
                            help="Actually write the backfilled costs (default is a safe dry-run).")
        parser.add_argument("--all", action="store_true",
                            help="Process all confirmed orders, not just cost_production==0")

    def handle(self, *args, **opts):
        dry_run = not opts["apply"]
        s = backfill_order_costs(only_zero=not opts["all"], dry_run=dry_run)
        mode = "DRY-RUN (no changes written)" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] examined={s['examined']} would_update={s['updated']} "
            f"full_cost={s['full_cost']} partial_cost={s['partial_cost']} "
            f"no_cost_data={s['no_cost_data']}"))
        if s["no_cost_data"]:
            self.stdout.write(self.style.WARNING(
                f"{s['no_cost_data']} order(s) had no matching Printify cost data — "
                f"production cost left at 0 (NOT fabricated). Sync those products first."))
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                "Dry-run only. Re-run with --apply to write the changes."))
