from threading import Event

from django.core.management.base import BaseCommand

from apps.workorders.scheduler import run_scheduler


class Command(BaseCommand):
    help = "Run the recurring work order scheduler continuously without Redis."

    def handle(self, *args, **options):
        stop = Event()
        self.stdout.write("Recurring work order scheduler started. Press Ctrl+C to stop.")
        try:
            run_scheduler(stop)
        except KeyboardInterrupt:
            stop.set()
