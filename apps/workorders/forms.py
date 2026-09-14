from datetime import timezone as dt_timezone
from uuid import UUID

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.utils.translation import gettext_lazy as _

from apps.assets.models import Equipment, EquipmentComponent
from apps.common.form_utils import remove_widget_attr, set_widget_attr
from apps.common.timezones import DEFAULT_TIMEZONE, US_TIMEZONE_CHOICES
from apps.facilities.access import accessible_warehouses

from .models import WorkOrder, WorkOrderTask
from .services import calculate_next_due


WORK_ORDER_INPUT_FIELDS = (
    "schedule_type",
    "warehouse",
    "equipment",
    "component",
    "title",
    "description",
    "work_type",
    "priority",
    "timezone",
    "due_at",
    "task_duration_hours",
    "recurrence_unit",
    "recurrence_interval",
    "recurrence_end_at",
    "assignee",
)

WORK_ORDER_INPUT_WIDGETS = {
    "due_at": forms.DateTimeInput(
        attrs={"type": "datetime-local"},
        format="%Y-%m-%dT%H:%M",
    ),
    "task_duration_hours": forms.NumberInput(attrs={"min": 1, "step": 1}),
    "recurrence_end_at": forms.DateTimeInput(
        attrs={"type": "datetime-local"},
        format="%Y-%m-%dT%H:%M",
    ),
    "description": forms.Textarea(attrs={"rows": 4}),
}


class WorkOrderDateTimeField(forms.DateTimeField):
    timezone_name = DEFAULT_TIMEZONE

    def to_python(self, value):
        # Django validates ambiguous/nonexistent local times during DST changes.
        with django_timezone.override(self.timezone_name):
            parsed = super().to_python(value)
        return parsed.astimezone(dt_timezone.utc) if parsed else None

    def prepare_value(self, value):
        with django_timezone.override(self.timezone_name):
            return super().prepare_value(value)


WORK_ORDER_TIME_FIELDS = {
    "due_at": WorkOrderDateTimeField,
    "recurrence_end_at": WorkOrderDateTimeField,
}


class WorkOrderDependencyMixin:
    def __init__(self, *args, user=None, **kwargs):
        allowed_zones = dict(US_TIMEZONE_CHOICES)
        instance = kwargs.get("instance")
        if instance is None or instance._state.adding:
            initial = dict(kwargs.get("initial") or {})
            user_zone = getattr(user, "timezone", DEFAULT_TIMEZONE)
            initial.setdefault("timezone", user_zone if user_zone in allowed_zones else DEFAULT_TIMEZONE)
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        selected_zone = (
            self.data.get(self.add_prefix("timezone")) if self.is_bound
            else self.initial.get("timezone", DEFAULT_TIMEZONE)
        )
        field_zone = selected_zone if selected_zone in allowed_zones else DEFAULT_TIMEZONE
        for name in WORK_ORDER_TIME_FIELDS:
            self.fields[name].timezone_name = field_zone
        warehouses = accessible_warehouses(user)
        self.fields["warehouse"].queryset = warehouses
        set_widget_attr(
            self.fields["warehouse"],
            "data-options-url",
            reverse("workorders:options"),
        )
        labels = {
            "data-label-select-warehouse": _("请先选择仓库"),
            "data-label-select-equipment": _("请先选择设备"),
            "data-label-loading": _("正在加载…"),
            "data-label-choose-equipment": _("请选择设备"),
            "data-label-no-equipment": _("该仓库没有可用设备"),
            "data-label-unassigned": _("待认领（不指定负责人）"),
            "data-label-no-assignee": _("该仓库没有可接单人员"),
            "data-label-whole-equipment": _("整机（不选择部件）"),
            "data-label-no-components": _("整机（没有已登记部件）"),
            "data-label-equipment-error": _("设备加载失败"),
            "data-label-assignee-error": _("负责人加载失败"),
            "data-label-component-error": _("部件加载失败"),
        }
        for attribute, label in labels.items():
            set_widget_attr(self.fields["warehouse"], attribute, label)

        warehouse_id = self._uuid_or_none(self._selected_id("warehouse"))
        equipment_id = self._uuid_or_none(self._selected_id("equipment"))
        selected_warehouse = warehouses.filter(pk=warehouse_id).first() if warehouse_id else None
        selected_equipment = None
        equipment = Equipment.objects.none()

        if selected_warehouse:
            equipment = Equipment.objects.filter(warehouse=selected_warehouse).filter(
                ~Q(status=Equipment.Status.RETIRED)
                | Q(pk=getattr(self.instance, "equipment_id", None))
            )
            selected_equipment = equipment.filter(pk=equipment_id).first() if equipment_id else None

        self.fields["equipment"].queryset = equipment.order_by("asset_code")
        self.fields["component"].queryset = (
            EquipmentComponent.objects.filter(equipment=selected_equipment)
            .filter(
                Q(status=EquipmentComponent.Status.ACTIVE)
                | Q(pk=getattr(self.instance, "component_id", None))
            )
            .order_by("code")
            if selected_equipment
            else EquipmentComponent.objects.none()
        )
        self.fields["assignee"].queryset = (
            get_user_model()
            .objects.filter(
                warehouse_memberships__warehouse=selected_warehouse,
                warehouse_memberships__is_active=True,
                warehouse_memberships__role__is_active=True,
                warehouse_memberships__role__can_receive_work_orders=True,
                is_active=True,
            )
            .distinct()
            .order_by("display_name", "username")
            if selected_warehouse
            else get_user_model().objects.none()
        )

        self.fields["equipment"].empty_label = _("请先选择仓库") if not selected_warehouse else _("请选择设备")
        self.fields["component"].empty_label = _("请先选择设备") if not selected_equipment else _("整机（不选择部件）")
        self.fields["assignee"].empty_label = _("请先选择仓库") if not selected_warehouse else _("待认领（不指定负责人）")

        dependent_fields = {
            "equipment": not selected_warehouse,
            "component": not selected_equipment,
            "assignee": not selected_warehouse,
        }
        for name, disabled in dependent_fields.items():
            field = self.fields[name]
            set_widget_attr(field, "data-dependent-field", name)
            if disabled:
                set_widget_attr(field, "disabled", True)
            else:
                remove_widget_attr(field, "disabled")

        # These inputs are conditional. Disabled browser inputs are omitted from
        # POST data when the user creates a one-time work order.
        self.fields["recurrence_unit"].required = False
        self.fields["recurrence_interval"].required = False
        self.fields["recurrence_end_at"].required = False

    def clean(self):
        cleaned_data = super().clean()
        schedule_type = cleaned_data.get("schedule_type")
        due_at = cleaned_data.get("due_at")
        recurrence_end_at = cleaned_data.get("recurrence_end_at")
        if schedule_type == WorkOrder.ScheduleType.RECURRING:
            if not cleaned_data.get("recurrence_unit"):
                self.add_error("recurrence_unit", _("请选择周期单位。"))
            if (cleaned_data.get("recurrence_interval") or 0) < 1:
                self.add_error("recurrence_interval", _("周期数值必须大于 0。"))
            if due_at and recurrence_end_at and recurrence_end_at <= due_at:
                self.add_error(
                    "recurrence_end_at",
                    _("周期结束时间必须晚于工单开始生成日期。"),
                )
        return cleaned_data

    def save(self, commit=True):
        work_order = super().save(commit=False)
        if work_order.schedule_type == WorkOrder.ScheduleType.RECURRING:
            work_order.recurrence_number = work_order.recurrence_number or 1
            changed_schedule = self.instance._state.adding or bool(
                {"schedule_type", "timezone", "due_at", "recurrence_unit", "recurrence_interval"} & set(self.changed_data)
            )
            if changed_schedule or not work_order.next_occurrence_at:
                last_occurrence = (
                    work_order.generated_occurrences.order_by("-due_at").first()
                    if not changed_schedule and not work_order._state.adding
                    else None
                )
                work_order.next_occurrence_at = calculate_next_due(
                    last_occurrence.due_at if last_occurrence else work_order.due_at,
                    work_order.recurrence_unit,
                    work_order.recurrence_interval,
                    timezone_name=work_order.timezone,
                    anchor=work_order.due_at,
                )
            if "recurrence_active" not in self.fields:
                work_order.recurrence_active = True
            elif "schedule_type" in self.changed_data:
                work_order.recurrence_active = True
            if (
                work_order.recurrence_end_at
                and work_order.next_occurrence_at > work_order.recurrence_end_at
            ):
                work_order.recurrence_active = False
                work_order.next_occurrence_at = None
        elif not work_order.recurrence_source_id:
            work_order.recurrence_unit = ""
            work_order.recurrence_interval = 1
            work_order.recurrence_end_at = None
            work_order.next_occurrence_at = None
            work_order.recurrence_active = False
        if commit:
            work_order.save()
            self.save_m2m()
        return work_order

    def _selected_id(self, field_name):
        if self.is_bound:
            return self.data.get(self.add_prefix(field_name))
        initial = self.initial.get(field_name)
        if hasattr(initial, "pk"):
            return initial.pk
        if initial:
            return initial
        if self.instance and self.instance.pk:
            return getattr(self.instance, f"{field_name}_id", None)
        return None

    @staticmethod
    def _uuid_or_none(value):
        try:
            return UUID(str(value)) if value else None
        except (TypeError, ValueError, AttributeError):
            return None


class WorkOrderCreateForm(WorkOrderDependencyMixin, forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = WORK_ORDER_INPUT_FIELDS
        widgets = WORK_ORDER_INPUT_WIDGETS
        field_classes = WORK_ORDER_TIME_FIELDS


class WorkOrderTaskCreateForm(forms.ModelForm):
    class Meta:
        model = WorkOrderTask
        fields = ("title", "instructions", "requires_photo")
        widgets = {"instructions": forms.Textarea(attrs={"rows": 2})}


WorkOrderTaskCreateFormSet = forms.formset_factory(
    WorkOrderTaskCreateForm,
    extra=1,
    can_delete=True,
)


class WorkOrderAdminForm(WorkOrderCreateForm):
    """Admin add form: intentionally identical to the public create form."""


class WorkOrderAdminChangeForm(WorkOrderDependencyMixin, forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = WORK_ORDER_INPUT_FIELDS + ("status", "recurrence_active")
        widgets = WORK_ORDER_INPUT_WIDGETS
        field_classes = WORK_ORDER_TIME_FIELDS
