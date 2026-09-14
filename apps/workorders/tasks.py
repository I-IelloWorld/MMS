from celery import shared_task

from .services import generate_recurring_work_orders


@shared_task(name="apps.workorders.tasks.generate_recurring_work_orders_task")
def generate_recurring_work_orders_task():
    return [str(work_order.id) for work_order in generate_recurring_work_orders()]
