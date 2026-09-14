from threading import Event, Thread

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as StaticRunserver

from apps.workorders.scheduler import run_scheduler


class Command(StaticRunserver):
    """Keep the local scheduler in the serving process, including autoreload."""

    def inner_run(self, *args, **options):
        self.scheduler_stop = Event()
        self.scheduler_thread = None
        try:
            return super().inner_run(*args, **options)
        finally:
            self.scheduler_stop.set()
            if self.scheduler_thread:
                self.scheduler_thread.join(timeout=5)

    def on_bind(self, server_port):
        super().on_bind(server_port)
        if settings.MMS_LOCAL_SCHEDULER and self.scheduler_thread is None:
            self.scheduler_thread = Thread(
                target=run_scheduler,
                args=(self.scheduler_stop,),
                name="mms-recurring-orders",
                daemon=True,
            )
            self.scheduler_thread.start()
            self.stdout.write(
                f"Recurring work order scheduler started (every {settings.MMS_SCHEDULER_INTERVAL_SECONDS}s)."
            )
