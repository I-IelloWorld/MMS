from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.facilities.access import filter_by_warehouse

from .forms import EquipmentImportForm
from .models import ImportBatch
from .services import process_equipment_import
from .workbooks import build_equipment_import_template


@login_required
def import_list(request):
    batches = filter_by_warehouse(
        ImportBatch.objects.select_related("warehouse", "created_by"),
        request.user,
    )
    return render(
        request,
        "data_imports/import_list.html",
        {"page": Paginator(batches, 25).get_page(request.GET.get("page"))},
    )


@login_required
def equipment_import(request):
    form = EquipmentImportForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        batch = form.save(commit=False)
        batch.created_by = request.user
        batch.save()
        process_equipment_import(batch)
        if batch.failed_rows:
            messages.warning(
                request,
                _("导入完成：成功 %(success)s 行，失败 %(failed)s 行。")
                % {"success": batch.success_rows, "failed": batch.failed_rows},
            )
        else:
            messages.success(
                request,
                _("导入完成：成功 %(success)s 行。") % {"success": batch.success_rows},
            )
        return redirect("data-imports:detail", pk=batch.id)
    return render(request, "data_imports/equipment_import.html", {"form": form})


@login_required
def equipment_import_template(request):
    content = build_equipment_import_template(request.user)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="MMS_equipment_import_template.xlsx"'
    )
    return response


@login_required
def import_detail(request, pk):
    batch = get_object_or_404(
        filter_by_warehouse(
            ImportBatch.objects.select_related("warehouse", "created_by").prefetch_related("errors"),
            request.user,
        ),
        pk=pk,
    )
    return render(request, "data_imports/import_detail.html", {"batch": batch})

# Create your views here.
