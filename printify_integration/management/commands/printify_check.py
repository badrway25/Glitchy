from django.core.management.base import BaseCommand
from django.conf import settings
from printify_integration.printify_client import PrintifyClient

class Command(BaseCommand):
    help = "Check Printify token and show shops"

    def handle(self, *args, **kwargs):
        client = PrintifyClient(settings.PRINTIFY_API_TOKEN)
        shops = client.get_shops()
        self.stdout.write(self.style.SUCCESS(f"Found {len(shops)} shop(s)"))
        for s in shops:
            self.stdout.write(f"- id={s.get('id')} title={s.get('title')}")
