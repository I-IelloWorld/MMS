from datetime import timedelta, timezone as dt_timezone
from math import ceil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel
from apps.common.timezones import DEFAULT_TIMEZONE, US_TIMEZONE_CHOICES


class WorkOrder(TimeStampedModel):
    class ScheduleType(models.TextChoices):
        ONE_TIME = "ONE_TIME", _("一次性工单")
        RECURRING = "RECURRING", _("周期性工单")

    class CycleUnit(models.TextChoices):
        DAY = "DAY", _("天")
        WEEK = "WEEK", _("周")
        MONTH = "MONTH", _("月")
        QUARTER = "QUARTER", _("季度")
        YEAR = "YEAR", _("年")

    class Type(models.TextChoices):
        PREVENTIVE = "PREVENTIVE", _("预防性维保")
        CORRECTIVE = "CORRECTIVE", _("故障维修")
        INSPECTION = "INSPECTION", _("巡检")

    class Priority(models.TextChoices):
        LOW = "LOW", _("低")
        MEDIUM = "MEDIUM", _("中")
        HIGH = "HIGH", _("高")
        CRITICAL = "CRITICAL", _("紧急")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("草稿")
        OPEN = "OPEN", _("待分派")
        ASSIGNED = "ASSIGNED", _("已分派")
        IN_PROGRESS = "IN_PROGRESS", _("进行中")
        COMPLETED = "COMPLETED", _("待验收")
        CLOSED = "CLOSED", _("已关闭")
        CANCELLED = "CANCELLED", _("已取消")

    number = models.CharField(_("工单编号"), max_length=32, unique=True)
    warehouse = models.ForeignKey("facilities.Warehouse", verbose_name=_("仓库"), on_delete=models.PROTECT, related_name="work_orders")
    equipment = models.ForeignKey("assets.Equipment", verbose_name=_("设备"), on_delete=models.PROTECT, related_name="work_orders")
    component = models.ForeignKey("assets.EquipmentComponent", verbose_name=_("部件"), on_delete=models.PROTECT, null=True, blank=True, related_name="work_orders")
    work_type = models.CharField(_("工单类型"), max_length=16, choices=Type.choices, default=Type.PREVENTIVE)
    priority = models.CharField(_("优先级"), max_length=16, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    status = models.CharField(_("状态"), max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    title = models.CharField(_("标题"), max_length=180)
    description = models.TextField(_("说明"), blank=True)
    timezone = models.CharField(
        _("工单时区"), max_length=64,
        choices=US_TIMEZONE_CHOICES, default=DEFAULT_TIMEZONE,
    )
    due_at = models.DateTimeField(
        _("工单开始生成日期"),
        db_index=True,
        help_text=_(
            "工单从该时间开始出现在相关人员的工作台；周期性工单从该时间计算后续生成时间。"
        ),
    )
    task_duration_hours = models.PositiveIntegerField(
        _("任务时间"),
        default=24,
        validators=[MinValueValidator(1)],
        help_text=_("从工单开始生成起允许的处理时长，单位为小时。"),
    )
    schedule_type = models.CharField(
        _("工单频率"),
        max_length=16,
        choices=ScheduleType.choices,
        default=ScheduleType.ONE_TIME,
        db_index=True,
    )
    recurrence_unit = models.CharField(
        _("周期单位"),
        max_length=16,
        choices=CycleUnit.choices,
        blank=True,
    )
    recurrence_interval = models.PositiveIntegerField(_("周期数值"), default=1, validators=[MinValueValidator(1)])
    recurrence_end_at = models.DateTimeField(_("周期结束时间"), null=True, blank=True)
    next_occurrence_at = models.DateTimeField(_("下次生成时间"), null=True, blank=True, db_index=True)
    recurrence_active = models.BooleanField(_("周期有效"), default=False, db_index=True)
    recurrence_source = models.ForeignKey(
        "self",
        verbose_name=_("周期来源工单"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="generated_occurrences",
    )
    recurrence_number = models.PositiveIntegerField(
        _("周期期次"), null=True, blank=True, editable=False,
        validators=[MinValueValidator(1)],
    )
    last_recurrence_number = models.PositiveIntegerField(
        _("最近生成期次"), default=1, editable=False,
        validators=[MinValueValidator(1)],
    )
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("负责人"), on_delete=models.PROTECT, null=True, blank=True, related_name="assigned_work_orders")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("创建人"), on_delete=models.SET_NULL, null=True, blank=True, related_name="created_work_orders")
    started_at = models.DateTimeField(_("开始时间"), null=True, blank=True)
    completed_at = models.DateTimeField(_("完成时间"), null=True, blank=True)
    closed_at = models.DateTimeField(_("关闭时间"), null=True, blank=True)

    class Meta:
        verbose_name = _("维保工单")
        verbose_name_plural = _("维保工单")
        ordering = ["due_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(schedule_type="RECURRING") | Q(recurrence_interval__gte=1),
                name="recurring_interval_positive",
            ),
            models.UniqueConstraint(
                fields=["recurrence_source", "due_at"],
                condition=Q(recurrence_source__isnull=False),
                name="uniq_recurring_work_order_occurrence",
            ),
            models.UniqueConstraint(
                fields=["recurrence_source", "recurrence_number"],
                condition=Q(recurrence_source__isnull=False, recurrence_number__isnull=False),
                name="uniq_recurring_work_order_number",
            ),
        ]
        indexes = [models.Index(fields=["warehouse", "status", "due_at"])]

    def clean(self):
        errors = {}
        if self.equipment_id and self.warehouse_id and self.equipment.warehouse_id != self.warehouse_id:
            errors["equipment"] = _("设备必须属于工单仓库。")
        if self.component_id and self.component.equipment_id != self.equipment_id:
            errors["component"] = _("部件必须属于工单设备。")
        if self.assignee_id and self.warehouse_id:
            is_engineer = self.assignee.warehouse_memberships.filter(
                warehouse_id=self.warehouse_id,
                is_active=True,
                role__is_active=True,
                role__can_receive_work_orders=True,
            ).exists()
            if not is_engineer:
                errors["assignee"] = _("负责人必须具有该仓库角色的接单权限。")
        if self.schedule_type == self.ScheduleType.RECURRING:
            if not self.recurrence_unit:
                errors["recurrence_unit"] = _("周期性工单必须选择周期单位。")
            if self.recurrence_interval < 1:
                errors["recurrence_interval"] = _("周期数值必须大于 0。")
            if self.recurrence_end_at and self.due_at and self.recurrence_end_at <= self.due_at:
                errors["recurrence_end_at"] = _(
                    "周期结束时间必须晚于工单开始生成日期。"
                )
        elif self.recurrence_source_id is None and (
            self.recurrence_unit or self.next_occurrence_at or self.recurrence_active
        ):
            errors["schedule_type"] = _("一次性工单不能包含周期设置。")
        if errors:
            raise ValidationError(errors)

    @property
    def recurrence_label(self):
        number = self.recurrence_number
        if number is None and self.schedule_type == self.ScheduleType.RECURRING:
            number = 1
        return _("（第 %(number)s 期）") % {"number": number} if number else ""

    @property
    def display_title(self):
        # Keep the editable title separate so labels follow the viewer's language.
        return f"{self.title} {self.recurrence_label}" if self.recurrence_label else self.title

    @property
    def is_overdue(self):
        from django.utils import timezone

        terminal = {self.Status.COMPLETED, self.Status.CLOSED, self.Status.CANCELLED}
        return self.status not in terminal and self.deadline_at < timezone.now()

    @property
    def deadline_at(self):
        return self.due_at.astimezone(dt_timezone.utc) + timedelta(hours=self.task_duration_hours)

    @property
    def remaining_hours(self):
        from django.utils import timezone

        terminal = {self.Status.COMPLETED, self.Status.CLOSED, self.Status.CANCELLED}
        if self.status in terminal:
            return None
        seconds = (self.deadline_at - timezone.now()).total_seconds()
        return max(0, ceil(seconds / 3600))

    def __str__(self):
        return f"{self.number} · {self.display_title}"


class WorkOrderTask(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("未开始")
        DONE = "DONE", _("已完成")
        NOT_APPLICABLE = "NOT_APPLICABLE", _("不适用")

    work_order = models.ForeignKey(WorkOrder, verbose_name=_("工单"), on_delete=models.CASCADE, related_name="tasks")
    sequence = models.PositiveIntegerField(_("顺序"))
    title = models.CharField(_("任务标题"), max_length=160)
    instructions = models.TextField(_("操作说明"), blank=True)
    requires_photo = models.BooleanField(_("必须上传照片"), default=False)
    status = models.CharField(_("状态"), max_length=24, choices=Status.choices, default=Status.PENDING)
    result = models.TextField(_("执行结果"), blank=True)
    photo = models.FileField(
        _("现场照片"),
        upload_to="work-order-task-photos/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("完成人"), on_delete=models.SET_NULL, null=True, blank=True, related_name="completed_work_order_tasks")
    completed_at = models.DateTimeField(_("完成时间"), null=True, blank=True)

    class Meta:
        verbose_name = _("工单任务")
        verbose_name_plural = _("工单任务")
        ordering = ["work_order", "sequence"]
        constraints = [models.UniqueConstraint(fields=["work_order", "sequence"], name="uniq_work_order_task_sequence")]

    def __str__(self):
        return f"{self.work_order.number} / {self.sequence}. {self.title}"


class WorkOrderLog(TimeStampedModel):
    work_order = models.ForeignKey(WorkOrder, verbose_name=_("工单"), on_delete=models.CASCADE, related_name="logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("操作者"), on_delete=models.SET_NULL, null=True, blank=True, related_name="work_order_logs")
    action = models.CharField(_("动作"), max_length=80)
    from_status = models.CharField(_("原状态"), max_length=16, blank=True)
    to_status = models.CharField(_("新状态"), max_length=16, blank=True)
    note = models.TextField(_("备注"), blank=True)

    class Meta:
        verbose_name = _("工单日志")
        verbose_name_plural = _("工单日志")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.work_order.number} / {self.action}"

# Create your models here.
