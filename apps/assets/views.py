from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET
from uuid import UUID

from apps.facilities.access import accessible_warehouses, filter_by_warehouse

from .forms import EquipmentCreateForm, can_modify_equipment
from .models import Equipment, EquipmentComponent


@login_required
def equipment_list(request):
    equipment = filter_by_warehouse(
        Equipment.objects.select_related("warehouse", "category"),
        request.user,
    )
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse", "")
    status = request.GET.get("status", "")
    if query:
        equipment = equipment.filter(
            Q(asset_code__icontains=query)
            | Q(name__icontains=query)
            | Q(serial_number__icontains=query)
            | Q(location_detail__icontains=query)
        )
    if warehouse_id:
        equipment = equipment.filter(warehouse_id=warehouse_id)
    if status:
        equipment = equipment.filter(status=status)
    page = Paginator(equipment, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "assets/equipment_list.html",
        {
            "page": page,
            "warehouses": accessible_warehouses(request.user),
            "status_choices": Equipment.Status.choices,
            "filters": {"q": query, "warehouse": warehouse_id, "status": status},
            "can_modify_equipment": can_modify_equipment(request.user),
        },
    )


@login_required
def equipment_create(request):
    if not can_modify_equipment(request.user):
        raise PermissionDenied(_("你没有录入设备的权限。"))
    form = EquipmentCreateForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        equipment = form.save()
        messages.success(
            request,
            _("设备 %(code)s 已创建。") % {"code": equipment.asset_code},
        )
        return redirect("assets:equipment-detail", pk=equipment.pk)
    return render(request, "assets/equipment_form.html", {"form": form})


@login_required
def equipment_detail(request, pk):
    equipment = get_object_or_404(
        filter_by_warehouse(
            Equipment.objects.select_related("warehouse", "category").prefetch_related("components", "work_orders"),
            request.user,
        ),
        pk=pk,
    )
    return render(
        request,
        "assets/equipment_detail.html",
        {
            "equipment": equipment,
            "can_modify_equipment": can_modify_equipment(request.user),
        },
    )


@login_required
@require_GET
def component_options(request):
    response = {"components": []}
    equipment_id = _uuid_or_none(request.GET.get("equipment", ""))
    excluded_id = _uuid_or_none(request.GET.get("exclude", ""))
    if not equipment_id:
        return JsonResponse(response)

    equipment = (
        Equipment.objects.filter(warehouse__in=accessible_warehouses(request.user))
        .filter(pk=equipment_id)
        .first()
    )
    if not equipment:
        return JsonResponse(response)

    components = EquipmentComponent.objects.filter(
        equipment=equipment,
        status=EquipmentComponent.Status.ACTIVE,
    ).exclude(pk=excluded_id).order_by("code")
    response["components"] = [
        {"value": str(component.id), "label": f"{component.code} · {component.name}"}
        for component in components
    ]
    return JsonResponse(response)


def _uuid_or_none(value):
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError, AttributeError):
        return None

# Create your views here.
