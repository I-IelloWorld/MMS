from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.notifications.models import Notification

from .models import WorkOrder, WorkOrderTask


@receiver(post_delete, sender=WorkOrder)
def delete_work_order_notifications(sender, instance, **kwargs):
    Notification.objects.filter(
        entity_type="workorder",
        entity_id=instance.pk,
    ).delete()


@receiver(post_delete, sender=WorkOrderTask)
def delete_work_order_task_artifacts(sender, instance, **kwargs):
    Notification.objects.filter(
        entity_type__in=("workordertask", "work_order_task"),
        entity_id=instance.pk,
    ).delete()
    if instance.photo:
        instance.photo.delete(save=False)
