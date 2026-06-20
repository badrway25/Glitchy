from django.core.management.base import BaseCommand

from notifications.dispatcher import retry_pending


class Command(BaseCommand):
    help = "Retry failed/pending outbound n8n events"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **opts):
        sent = retry_pending(limit=opts["limit"])
        self.stdout.write(self.style.SUCCESS(f"Retried events; {sent} delivered."))
