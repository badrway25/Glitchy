"""Sync Printify shipping profiles into the persistent table (safe, no order push).

    python manage.py printify_sync_shipping_profiles                 # dry-run (default)
    python manage.py printify_sync_shipping_profiles --apply
    python manage.py printify_sync_shipping_profiles --apply --country IT --country US
    python manage.py printify_sync_shipping_profiles --product-id 6 --json

Output is safe: counts, country codes, warnings — never a token or PII.
"""
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import Printify shipping profiles (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the profiles (default is a safe dry-run).")
        parser.add_argument("--product-id", type=int, default=None)
        parser.add_argument("--country", action="append", default=None,
                            help="Limit to country code(s); repeatable.")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        from printify_integration.profiles import sync_all_shipping_profiles
        dry_run = not opts["apply"]
        total, results = sync_all_shipping_profiles(
            dry_run=dry_run, countries=opts["country"],
            product_id=opts["product_id"], limit=opts["limit"])
        mode = "DRY-RUN (no changes written)" if dry_run else "APPLIED"

        if opts["json"]:
            self.stdout.write(json.dumps({"mode": mode, "summary": {
                "pairs": total["pairs"], "created": total["created"],
                "updated": total["updated"], "countries": total["countries"],
                "errors": len(total["errors"])}}, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] blueprint/provider pairs={total['pairs']} created={total['created']} "
            f"updated={total['updated']} countries={','.join(total['countries']) or '—'}"))
        if total["errors"]:
            for e in total["errors"]:
                self.stdout.write(self.style.WARNING(
                    f"  bp{e['blueprint_id']}/pr{e['provider_id']}: {e['error']}"))
        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run only. Re-run with --apply to write."))
