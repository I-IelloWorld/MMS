import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from uuid import UUID

from apps.assets.models import Equipment, EquipmentComponent
from apps.facilities.access import accessible_warehouses, filter_by_warehouse
from apps.facilities.models import WarehouseMembership

from .forms import WorkOrderCreateForm, WorkOrderTaskCreateFormSet
from .models import WorkOrder, WorkOrderTask
from .permissions import can_manage_work_orders
from .services import (
    complete_work_order_task,
    generate_recurring_work_orders,
    notify_work_order_created,
    take_work_order,
    transition_work_order,
    work_order_number,
)


@require_GET
@never_cache
def generate_recurring_work_orders_cron(request):
    """Run the idempotent recurring-order scan from Vercel Cron."""
    if not settings.CRON_SECRET:
        return JsonResponse({"detail": "Scheduler is not configured."}, status=503)
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.CRON_SECRET}"
    if not secrets.compare_digest(supplied, expected):
        return JsonResponse({"detail": "Unauthorized."}, status=401)
    created = generate_recurring_work_orders(
        max_occurrences=settings.MMS_CRON_MAX_OCCURRENCES,
    )
    return JsonResponse(
        {"generated": len(created), "work_order_ids": [str(order.id) for order in created]}
    )


def _permissions(user, work_order):
    if user.is_superuser:
        return True, True
    membership = WarehouseMembership.objects.filter(
        warehouse=work_order.warehouse,
        user=user,
        is_active=True,
    ).first()
    if not membership:
        return False, False
    can_manage = membership.role.is_active and membership.role.can_manage_work_orders
    can_execute = can_manage or work_order.assignee_id in {None, user.id}
    return can_manage, can_execute


@login_required
def work_order_list(request):
    work_orders = filter_by_warehouse(
        WorkOrder.objects.select_related("warehouse", "equipment", "component", "assignee"),
        request.user,
    )
    warehouse_id = request.GET.get("warehouse", "")
    status = request.GET.get("status", "")
    scope = request.GET.get("scope", "")
    schedule_type = request.GET.get("schedule_type", "")
    if warehouse_id:
        work_orders = work_orders.filter(warehouse_id=warehouse_id)
    if status:
        work_orders = work_orders.filter(status=status)
    if scope == "mine":
        work_orders = work_orders.filter(assignee=request.user)
    if schedule_type:
        work_orders = work_orders.filter(schedule_type=schedule_type)
    return render(
        request,
        "workorders/work_order_list.html",
        {
            "page": Paginator(work_orders, 25).get_page(request.GET.get("page")),
            "warehouses": accessible_warehouses(request.user),
            "status_choices": WorkOrder.Status.choices,
            "schedule_choices": WorkOrder.ScheduleType.choices,
            "filters": {
                "warehouse": warehouse_id,
                "status": status,
                "scope": scope,
                "schedule_type": schedule_type,
            },
            "can_manage_work_orders": can_manage_work_orders(request.user),
        },
    )


@login_required
@transaction.atomic
def work_order_create(request):
    if not can_manage_work_orders(request.user):
        raise PermissionDenied(_("你没有创建工单的权限。"))
    form = WorkOrderCreateForm(request.POST or None, user=request.user)
    has_task_data = request.method == "POST" and "tasks-TOTAL_FORMS" in request.POST
    task_formset = WorkOrderTaskCreateFormSet(
        request.POST if has_task_data else None,
        prefix="tasks",
    )
    tasks_are_valid = task_formset.is_valid() if has_task_data else True
    if request.method == "POST" and form.is_valid() and tasks_are_valid:
        work_order = form.save(commit=False)
        work_order.number = work_order_number()
        work_order.created_by = request.user
        work_order.status = (
            WorkOrder.Status.ASSIGNED if work_order.assignee_id else WorkOrder.Status.OPEN
        )
        work_order.save()
        task_rows = (
            task_formset.cleaned_data
            if has_task_data
            else []
        )
        sequence = 1
        for task_data in task_rows:
            if not task_data or task_data.get("DELETE"):
                continue
            WorkOrderTask.objects.create(
                work_order=work_order,
                sequence=sequence,
                title=task_data["title"].strip(),
                instructions=task_data.get("instructions", "").strip(),
                requires_photo=task_data.get("requires_photo", False),
            )
            sequence += 1
        notify_work_order_created(work_order)
        messages.success(
            request,
            _("工单 %(number)s 已创建。") % {"number": work_order.number},
        )
        return redirect("workorders:detail", pk=work_order.id)
    return render(
        request,
        "workorders/work_order_form.html",
        {"form": form, "task_formset": task_formset},
    )


@login_required
def work_order_detail(request, pk):
    work_order = get_object_or_404(
        filter_by_warehouse(
            WorkOrder.objects.select_related(
                "warehouse", "equipment", "component", "assignee", "recurrence_source"
            ).prefetch_related("tasks", "logs__actor"),
            request.user,
        ),
        pk=pk,
    )
    can_manage, can_execute = _permissions(request.user, work_order)
    if request.method == "POST":
        action = request.POST.get("action", "")
        note = request.POST.get("note", "")
        try:
            if action == "take" and can_execute:
                take_work_order(work_order.id, request.user)
            elif action.startswith("task:") and can_execute:
                complete_work_order_task(
                    action.split(":", 1)[1],
                    request.user,
                    note,
                    request.FILES.get("photo"),
                )
            elif action in {"start", "complete"} and can_execute:
                transition_work_order(work_order.id, action, request.user, note)
            elif action in {"close", "return"} and can_manage:
                transition_work_order(work_order.id, action, request.user, note)
            else:
                raise ValidationError(_("你没有权限执行该操作。"))
            messages.success(request, _("工单已更新。"))
        except (ValidationError, ValueError) as exc:
            messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
        return redirect("workorders:detail", pk=work_order.id)
    return render(
        request,
        "workorders/work_order_detail.html",
        {"work_order": work_order, "can_manage": can_manage, "can_execute": can_execute},
    )


@login_required
@require_GET
def work_order_options(request):
    response = {"equipment": [], "components": [], "assignees": []}
    warehouse_id = _uuid_or_none(request.GET.get("warehouse", ""))
    equipment_id = _uuid_or_none(request.GET.get("equipment", ""))
    warehouse = accessible_warehouses(request.user).filter(pk=warehouse_id).first() if warehouse_id else None
    if not warehouse:
        return JsonResponse(response)

    equipment = Equipment.objects.filter(
        warehouse=warehouse,
    ).exclude(status=Equipment.Status.RETIRED).order_by("asset_code")
    response["equipment"] = [
        {"value": str(item.id), "label": f"{item.asset_code} · {item.name}"}
        for item in equipment
    ]
    memberships = (
        WarehouseMembership.objects.filter(
            warehouse=warehouse,
            is_active=True,
            role__is_active=True,
            role__can_receive_work_orders=True,
            user__is_active=True,
        )
        .select_related("user")
        .order_by("user__display_name", "user__username")
    )
    response["assignees"] = [
        {"value": str(membership.user_id), "label": f"{membership.user} · {membership.get_role_display()}"}
        for membership in memberships
    ]

    selected_equipment = equipment.filter(pk=equipment_id).first() if equipment_id else None
    if not selected_equipment:
        return JsonResponse(response)

    components = EquipmentComponent.objects.filter(
        equipment=selected_equipment,
        status=EquipmentComponent.Status.ACTIVE,
    ).order_by("code")
    response["components"] = [
        {"value": str(item.id), "label": f"{item.code} · {item.name}"}
        for item in components
    ]
    return JsonResponse(response)


def _uuid_or_none(value):
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError, AttributeError):
        return None

# Create your views here.
