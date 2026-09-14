from django.core.management.base import BaseCommand

from apps.workorders.services import generate_recurring_work_orders


class Command(BaseCommand):
    help = "Generate due occurrences from active recurring work orders."

    def handle(self, *args, **options):
        created = generate_recurring_work_orders()
        self.stdout.write(self.style.SUCCESS(f"Generated {len(created)} work order(s)."))
