from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.assets.models import Equipment
from apps.facilities.access import accessible_warehouses, filter_by_warehouse
from apps.workorders.models import WorkOrder
from apps.workorders.permissions import can_manage_work_orders

from .reports import REPORT_TYPES, build_work_order_report


@login_required
def home(request):
    warehouses = accessible_warehouses(request.user)
    work_orders = filter_by_warehouse(
        WorkOrder.objects.select_related("warehouse", "equipment", "assignee"),
        request.user,
    )
    now = timezone.now()
    terminal = [WorkOrder.Status.COMPLETED, WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED]
    visible_work_orders = work_orders.filter(due_at__lte=now)
    active_visible_orders = visible_work_orders.exclude(status__in=terminal)
    stats = {
        "equipment": filter_by_warehouse(Equipment.objects.all(), request.user).filter(status=Equipment.Status.ACTIVE).count(),
        "open": active_visible_orders.count(),
        "overdue": sum(order.is_overdue for order in active_visible_orders),
        "due_week": work_orders.filter(due_at__range=(now, now + timedelta(days=7))).exclude(status__in=terminal).count(),
    }
    status_counts = {
        item["status"]: item["total"]
        for item in visible_work_orders.values("status").annotate(total=Count("id"))
    }
    recurring_orders = work_orders.filter(
        schedule_type=WorkOrder.ScheduleType.RECURRING,
        recurrence_active=True,
    ).order_by("next_occurrence_at")[:6]
    recent_work_orders = active_visible_orders.order_by("due_at")[:7]
    return render(
        request,
        "dashboard/home.html",
        {
            "warehouses": warehouses,
            "stats": stats,
            "status_counts": status_counts,
            "recurring_orders": recurring_orders,
            "recent_work_orders": recent_work_orders,
            "now": now,
            "can_manage_work_orders": can_manage_work_orders(request.user),
        },
    )


@login_required
def export_work_order_report(request, report_type):
    if report_type not in REPORT_TYPES:
        raise Http404
    content, start_date, end_date = build_work_order_report(
        request.user,
        report_type,
    )
    period = str(start_date) if report_type == "daily" else f"{start_date}_to_{end_date}"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="MMS_{report_type}_{period}.xlsx"'
    )
    return response

# Create your views here.
