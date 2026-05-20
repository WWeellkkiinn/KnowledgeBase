"""Management command: import journals seed data."""
from django.core.management.base import BaseCommand

from journals.services import bootstrap_from_seed


class Command(BaseCommand):
    help = "Import journals from seed/journals.json"

    def handle(self, *args, **options):
        result = bootstrap_from_seed()
        self.stdout.write(
            f"Seed done: inserted={result['inserted']} "
            f"updated={result['updated']} skipped={result['skipped']}"
        )
