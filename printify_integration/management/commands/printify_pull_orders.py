from django.core.management.base import BaseCommand

from printify_integration.services import pull_order_statuses


class Command(BaseCommand):
    help = "Pull order status + tracking from Printify for recently-sent orders"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **opts):
        log = pull_order_statuses(limit=opts["limit"])
        style = self.style.SUCCESS if log.status in ("ok", "partial") else self.style.ERROR
        self.stdout.write(style(
            f"[{log.get_status_display()}] orders updated={log.updated_count} "
            f"errors={log.error_count} :: {log.message}"
        ))
