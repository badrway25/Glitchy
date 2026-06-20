from django.core.management.base import BaseCommand

from orders.services import backfill_order_costs


class Command(BaseCommand):
    help = ("Estimate costs/margins for historical orders (cost_production==0). "
            "Production cost is backfilled ONLY from real synced Printify data.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview without writing")
        parser.add_argument("--all", action="store_true",
                            help="Process all confirmed orders, not just cost_production==0")

    def handle(self, *args, **opts):
        s = backfill_order_costs(only_zero=not opts["all"], dry_run=opts["dry_run"])
        mode = "DRY-RUN" if opts["dry_run"] else "APPLIED"
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] examined={s['examined']} updated={s['updated']} "
            f"full_cost={s['full_cost']} partial_cost={s['partial_cost']} "
            f"no_cost_data={s['no_cost_data']}"))
        if s["no_cost_data"]:
            self.stdout.write(self.style.WARNING(
                f"{s['no_cost_data']} order(s) had no matching Printify cost data — "
                f"production cost left at 0 (not fabricated). Sync those products first."))
