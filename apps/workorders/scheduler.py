import logging

from django.conf import settings
from django.db import close_old_connections, connections

from .services import generate_recurring_work_orders


logger = logging.getLogger(__name__)


def run_scheduler(stop_event):
    """Run immediately, then scan periodically until the server shuts down."""
    interval = max(1, settings.MMS_SCHEDULER_INTERVAL_SECONDS)
    try:
        while not stop_event.is_set():
            close_old_connections()
            try:
                generated = generate_recurring_work_orders()
                if generated:
                    logger.info("Generated %s recurring work orders", len(generated))
            except Exception:
                # A transient DB lock must not permanently stop future scans.
                logger.exception("Recurring work order scan failed; retrying in %s seconds", interval)
            finally:
                close_old_connections()
            if stop_event.wait(interval):
                break
    finally:
        connections.close_all()
