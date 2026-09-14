from django import forms
from zoneinfo import ZoneInfo
from django.contrib import admin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.admin_mixins import RequestUserFormMixin

from .forms import WorkOrderAdminChangeForm, WorkOrderAdminForm, WorkOrderDateTimeField
from .models import WorkOrder, WorkOrderLog, WorkOrderTask
from .services import notify_work_order_created, work_order_number


class WorkOrderTaskInline(admin.TabularInline):
    model = WorkOrderTask
    extra = 1
    fields = ("sequence", "title", "instructions", "requires_photo")


class WorkOrderLogInline(admin.TabularInline):
    model = WorkOrderLog
    extra = 0
    readonly_fields = ("actor", "action", "from_status", "to_status", "note", "created_at")


@admin.register(WorkOrder)
class WorkOrderAdmin(RequestUserFormMixin, admin.ModelAdmin):
    form = WorkOrderAdminForm
    formfield_overrides = {
        models.DateTimeField: {
            "form_class": WorkOrderDateTimeField,
            "widget": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            )
        }
    }
    list_display = (
        "number",
        "title_with_cycle",
        "schedule_type",
        "warehouse",
        "equipment",
        "status",
        "priority",
        "assignee",
        "due_at_local",
        "timezone",
        "task_duration_hours",
    )
    list_filter = ("schedule_type", "recurrence_active", "warehouse", "status", "priority", "work_type")
    search_fields = ("number", "title", "equipment__asset_code", "equipment__name")
    readonly_fields = (
        "number",
        "created_by",
        "next_occurrence_local",
        "started_at_local",
        "completed_at_local",
        "closed_at_local",
    )
    inlines = (WorkOrderTaskInline, WorkOrderLogInline)

    @admin.display(description=_("标题"), ordering="title")
    def title_with_cycle(self, obj):
        return obj.display_title

    @staticmethod
    def _local_time(obj, value):
        return timezone.localtime(value, ZoneInfo(obj.timezone)).strftime("%Y-%m-%d %H:%M") if value else "-"

    @admin.display(description=_("工单开始生成日期"), ordering="due_at")
    def due_at_local(self, obj):
        return self._local_time(obj, obj.due_at)

    @admin.display(description=_("下次生成时间"))
    def next_occurrence_local(self, obj):
        return self._local_time(obj, obj.next_occurrence_at)

    @admin.display(description=_("开始时间"))
    def started_at_local(self, obj):
        return self._local_time(obj, obj.started_at)

    @admin.display(description=_("完成时间"))
    def completed_at_local(self, obj):
        return self._local_time(obj, obj.completed_at)

    @admin.display(description=_("关闭时间"))
    def closed_at_local(self, obj):
        return self._local_time(obj, obj.closed_at)

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["form"] = WorkOrderAdminChangeForm if obj else WorkOrderAdminForm
        return super().get_form(request, obj=obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    _("工单信息"),
                    {
                        "fields": (
                            "schedule_type",
                            "title",
                            "description",
                            "work_type",
                            "priority",
                            "timezone",
                            "due_at",
                            "task_duration_hours",
                        ),
                        "description": _(
                            "带 * 的字段为必填项；编号、状态和创建人由系统自动填写。"
                        ),
                    },
                ),
                (
                    _("仓库与维保对象"),
                    {"fields": ("warehouse", "equipment", "component", "assignee")},
                ),
                (
                    _("周期设置"),
                    {
                        "fields": (
                            "recurrence_unit",
                            "recurrence_interval",
                            "recurrence_end_at",
                        )
                    },
                ),
            )
        return (
            (
                _("系统信息"),
                {"fields": ("number", "status", "created_by")},
            ),
            (
                _("工单信息"),
                {
                    "fields": (
                        "schedule_type",
                        "title",
                        "description",
                        "work_type",
                        "priority",
                        "timezone",
                        "due_at",
                        "task_duration_hours",
                    )
                },
            ),
            (
                _("仓库与维保对象"),
                {"fields": ("warehouse", "equipment", "component", "assignee")},
            ),
            (
                _("周期设置"),
                {
                    "fields": (
                        "recurrence_unit",
                        "recurrence_interval",
                        "recurrence_end_at",
                        "next_occurrence_local",
                        "recurrence_active",
                    )
                },
            ),
            (
                _("执行信息"),
                {"fields": ("started_at_local", "completed_at_local", "closed_at_local")},
            ),
        )

    def get_inlines(self, request, obj):
        if obj is None:
            return [WorkOrderTaskInline]
        return super().get_inlines(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.number = work_order_number()
            obj.created_by = request.user
            obj.status = (
                WorkOrder.Status.ASSIGNED
                if obj.assignee_id
                else WorkOrder.Status.OPEN
            )
        super().save_model(request, obj, form, change)
        if not change:
            notify_work_order_created(obj)

    class Media:
        css = {"all": ("css/work-order-admin.css",)}
        js = ("js/work-order-form.js",)


admin.site.register(WorkOrderTask)
admin.site.register(WorkOrderLog)

# Register your models here.
