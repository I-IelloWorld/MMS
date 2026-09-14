from datetime import timedelta, timezone as dt_timezone
import logging
from uuid import uuid4
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from dateutil.tz import resolve_imaginary
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.facilities.models import WarehouseMembership
from apps.notifications.models import Notification, NotificationRecipient

from .models import WorkOrder, WorkOrderLog, WorkOrderTask

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    WorkOrder.Status.OPEN: {"assign": WorkOrder.Status.ASSIGNED},
    WorkOrder.Status.ASSIGNED: {"start": WorkOrder.Status.IN_PROGRESS},
    WorkOrder.Status.IN_PROGRESS: {"complete": WorkOrder.Status.COMPLETED},
    WorkOrder.Status.COMPLETED: {"close": WorkOrder.Status.CLOSED, "return": WorkOrder.Status.IN_PROGRESS},
}


def calculate_next_due(current_due, cycle_unit, cycle_value, timezone_name=None, anchor=None):
    if cycle_value < 1:
        raise ValueError("The recurrence interval must be greater than zero.")
    zone = ZoneInfo(timezone_name) if timezone_name else current_due.tzinfo
    local_due = current_due.astimezone(zone)
    local_anchor = anchor.astimezone(zone) if anchor else None
    if cycle_unit == WorkOrder.CycleUnit.DAY:
        following = local_due + timedelta(days=cycle_value)
    elif cycle_unit == WorkOrder.CycleUnit.WEEK:
        following = local_due + timedelta(weeks=cycle_value)
    elif cycle_unit in {WorkOrder.CycleUnit.MONTH, WorkOrder.CycleUnit.QUARTER}:
        months = cycle_value * (3 if cycle_unit == WorkOrder.CycleUnit.QUARTER else 1)
        following = local_due + relativedelta(months=months, day=local_anchor.day if local_anchor else None)
    elif cycle_unit == WorkOrder.CycleUnit.YEAR:
        following = local_due + relativedelta(
            years=cycle_value,
            month=local_anchor.month if local_anchor else None,
            day=local_anchor.day if local_anchor else None,
        )
    else:
        raise ValueError(f"Unsupported cycle unit: {cycle_unit}")
    if local_anchor:
        following = following.replace(
            hour=local_anchor.hour, minute=local_anchor.minute,
            second=local_anchor.second, microsecond=local_anchor.microsecond,
        )
    # Spring-forward gaps move by the DST gap; fall-back uses the first occurrence.
    # The original anchor restores the intended local time on the following day.
    following = resolve_imaginary(following.replace(fold=0))
    return following.astimezone(dt_timezone.utc)


def work_order_number():
    return f"WO-{timezone.localdate():%Y%m%d}-{uuid4().hex[:8].upper()}"


def _recipient_ids(work_order):
    if work_order.assignee_id:
        return [work_order.assignee_id]
    return list(
        WarehouseMembership.objects.filter(
            warehouse=work_order.warehouse,
            role__is_active=True,
            role__can_receive_work_orders=True,
            is_active=True,
            notification_enabled=True,
            user__is_active=True,
        ).values_list("user_id", flat=True)
    )


def notify_work_order_created(work_order, now=None):
    now = now or timezone.now()
    notification, _ = Notification.objects.get_or_create(
        dedup_key=f"workorder:{work_order.id}:created",
        defaults={
            "notification_type": Notification.Type.WORK_ORDER_CREATED,
            "title": f"新工单 {work_order.number}",
            "message": f"{work_order.warehouse.name} 的 {work_order.equipment.name} 有一项工单待处理。",
            "entity_type": "workorder",
            "entity_id": work_order.id,
        },
    )
    NotificationRecipient.objects.bulk_create(
        [
            NotificationRecipient(
                notification=notification,
                user_id=user_id,
                channel=NotificationRecipient.Channel.IN_APP,
                status=NotificationRecipient.Status.SENT,
                sent_at=now,
            )
            for user_id in _recipient_ids(work_order)
        ],
        ignore_conflicts=True,
    )
    return notification


@transaction.atomic
def create_recurring_occurrence(source_id, now=None):
    now = now or timezone.now()
    source = (
        WorkOrder.objects.select_for_update(of=("self",))
        .select_related("warehouse", "equipment", "component", "assignee", "created_by")
        .prefetch_related("tasks")
        .get(pk=source_id)
    )
    if (
        source.schedule_type != WorkOrder.ScheduleType.RECURRING
        or not source.recurrence_active
        or not source.next_occurrence_at
        or source.next_occurrence_at > now
        or source.status == WorkOrder.Status.CANCELLED
    ):
        return None, False

    scheduled_for = source.next_occurrence_at
    if source.recurrence_end_at and scheduled_for > source.recurrence_end_at:
        source.recurrence_active = False
        source.next_occurrence_at = None
        source.save(update_fields=["recurrence_active", "next_occurrence_at", "updated_at"])
        return None, False

    # Validate before creating anything so a bad schedule cannot loop forever.
    following_due = calculate_next_due(
        scheduled_for, source.recurrence_unit, source.recurrence_interval,
        timezone_name=source.timezone, anchor=source.due_at,
    )
    existing = WorkOrder.objects.filter(
        recurrence_source=source,
        due_at=scheduled_for,
    ).first()
    created = False
    occurrence = existing
    source.recurrence_number = source.recurrence_number or 1
    if not existing:
        status = WorkOrder.Status.ASSIGNED if source.assignee_id else WorkOrder.Status.OPEN
        occurrence = WorkOrder.objects.create(
            number=work_order_number(),
            warehouse=source.warehouse,
            equipment=source.equipment,
            component=source.component,
            work_type=source.work_type,
            priority=source.priority,
            status=status,
            title=source.title,
            description=source.description,
            timezone=source.timezone,
            due_at=scheduled_for,
            task_duration_hours=source.task_duration_hours,
            schedule_type=WorkOrder.ScheduleType.ONE_TIME,
            recurrence_source=source,
            recurrence_number=source.last_recurrence_number + 1,
            assignee=source.assignee,
            created_by=source.created_by,
        )
        WorkOrderTask.objects.bulk_create(
            [
                WorkOrderTask(
                    work_order=occurrence,
                    sequence=task.sequence,
                    title=task.title,
                    instructions=task.instructions,
                    requires_photo=task.requires_photo,
                )
                for task in source.tasks.all()
            ]
        )
        WorkOrderLog.objects.create(
            work_order=occurrence,
            action="GENERATED_FROM_RECURRING_ORDER",
            to_status=status,
            note=f"由周期工单 {source.number} 自动生成。",
        )
        notify_work_order_created(occurrence, now=now)
        created = True
    elif occurrence.recurrence_number is None:
        occurrence.recurrence_number = source.last_recurrence_number + 1
        occurrence.save(update_fields=["recurrence_number"])

    # Persist the counter on the source so deleting an occurrence cannot reuse it.
    source.last_recurrence_number = max(
        source.last_recurrence_number, occurrence.recurrence_number,
    )

    if source.recurrence_end_at and following_due > source.recurrence_end_at:
        source.recurrence_active = False
        source.next_occurrence_at = None
    else:
        source.next_occurrence_at = following_due
    source.save(update_fields=[
        "recurrence_active", "next_occurrence_at", "updated_at",
        "recurrence_number", "last_recurrence_number",
    ])
    return occurrence, created


def generate_recurring_work_orders(now=None, max_occurrences=None):
    now = now or timezone.now()
    created = []
    processed = 0
    source_ids = list(
        WorkOrder.objects.filter(
            schedule_type=WorkOrder.ScheduleType.RECURRING,
            recurrence_active=True,
            next_occurrence_at__lte=now,
        )
        .exclude(status=WorkOrder.Status.CANCELLED)
        .values_list("id", flat=True)
    )
    for source_id in source_ids:
        # Drain overdue occurrences using one transaction per occurrence.
        # The fixed scan time prevents generating any future occurrences.
        try:
            while True:
                if max_occurrences is not None and processed >= max_occurrences:
                    return created
                work_order, was_created = create_recurring_occurrence(source_id, now=now)
                if work_order is None:
                    break
                processed += 1
                if was_created:
                    created.append(work_order)
        except WorkOrder.DoesNotExist:
            continue
        except ValueError:
            logger.exception("Invalid recurrence on work order %s", source_id)
    return created


@transaction.atomic
def take_work_order(work_order_id, actor):
    work_order = WorkOrder.objects.select_for_update().get(pk=work_order_id)
    if work_order.status != WorkOrder.Status.OPEN or work_order.assignee_id:
        raise ValidationError("当前工单不能接单。")
    work_order.assignee = actor
    work_order.status = WorkOrder.Status.ASSIGNED
    work_order.save(update_fields=["assignee", "status", "updated_at"])
    WorkOrderLog.objects.create(
        work_order=work_order,
        actor=actor,
        action="TAKE",
        from_status=WorkOrder.Status.OPEN,
        to_status=WorkOrder.Status.ASSIGNED,
        note="工程师接单。",
    )
    return work_order


@transaction.atomic
def transition_work_order(work_order_id, action, actor, note=""):
    work_order = WorkOrder.objects.select_for_update().get(pk=work_order_id)
    target = ALLOWED_TRANSITIONS.get(work_order.status, {}).get(action)
    if not target:
        raise ValidationError("当前工单状态不允许执行该操作。")
    if action in {"return"} and not note.strip():
        raise ValidationError("退回工单必须填写原因。")
    if action == "complete" and work_order.tasks.filter(status=WorkOrderTask.Status.PENDING).exists():
        raise ValidationError("仍有未完成的任务，不能提交完成。")

    previous = work_order.status
    work_order.status = target
    update_fields = ["status", "updated_at"]
    if action == "start":
        work_order.started_at = timezone.now()
        update_fields.append("started_at")
    elif action == "complete":
        work_order.completed_at = timezone.now()
        update_fields.append("completed_at")
    elif action == "close":
        work_order.closed_at = timezone.now()
        update_fields.append("closed_at")
    work_order.save(update_fields=update_fields)
    WorkOrderLog.objects.create(
        work_order=work_order,
        actor=actor,
        action=action.upper(),
        from_status=previous,
        to_status=target,
        note=note.strip(),
    )
    return work_order


@transaction.atomic
def complete_work_order_task(task_id, actor, result="", photo=None):
    task = WorkOrderTask.objects.select_for_update().select_related("work_order").get(pk=task_id)
    if task.work_order.status != WorkOrder.Status.IN_PROGRESS:
        raise ValidationError("只有进行中的工单可以更新任务。")
    if task.requires_photo and not photo and not task.photo:
        raise ValidationError("该任务必须上传现场照片后才能完成。")
    if photo and (
        not getattr(photo, "content_type", "").startswith("image/")
        or photo.size > settings.MMS_MAX_UPLOAD_BYTES
    ):
        raise ValidationError("现场照片必须是 JPG、PNG 或 WebP 图片，且不超过 4 MB。")
    task.status = WorkOrderTask.Status.DONE
    task.result = result.strip()
    if photo:
        task.photo = photo
    task.completed_by = actor
    task.completed_at = timezone.now()
    task.full_clean()
    update_fields = ["status", "result", "completed_by", "completed_at", "updated_at"]
    if photo:
        update_fields.append("photo")
    task.save(update_fields=update_fields)
    WorkOrderLog.objects.create(
        work_order=task.work_order,
        actor=actor,
        action="TASK_COMPLETED",
        note=f"完成任务：{task.title}",
    )
    return task
