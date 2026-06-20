from django.core.management.base import BaseCommand

from printify_integration.services import sync_products


class Command(BaseCommand):
    help = "Sync Printify products into store.Product / store.Variation (with cost + sync log)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--max-pages", type=int, default=20)
        parser.add_argument("--category", type=str, default="Printify")
        parser.add_argument("--refresh-images", action="store_true")

    def handle(self, *args, **opts):
        log = sync_products(
            limit=opts["limit"],
            max_pages=opts["max_pages"],
            fallback_category_name=opts["category"],
            refresh_images=opts["refresh_images"],
        )
        style = self.style.SUCCESS if log.status in ("ok", "partial") else self.style.ERROR
        self.stdout.write(style(
            f"[{log.get_status_display()}] products +{log.created_count} "
            f"~{log.updated_count} errors={log.error_count} :: {log.message}"
        ))
