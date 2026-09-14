from uuid import UUID

from django import forms
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.common.form_utils import remove_widget_attr, set_widget_attr
from apps.facilities.access import accessible_warehouses

from .models import AssetCategory, Equipment, EquipmentComponent


class EquipmentCreateForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = (
            "warehouse",
            "category",
            "asset_code",
            "name",
            "manufacturer",
            "model",
            "serial_number",
            "commissioned_on",
            "location_detail",
            "criticality",
            "status",
        )
        widgets = {
            "commissioned_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = accessible_warehouses(user).filter(
            status="ACTIVE"
        )
        self.fields["category"].queryset = AssetCategory.objects.filter(
            is_active=True
        ).order_by("code")
        self.fields["warehouse"].empty_label = _("请选择仓库")
        self.fields["category"].empty_label = _("请选择设备分类")


def can_modify_equipment(user):
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.has_perm("assets.modify_equipment")
            or user.has_perm("assets.add_equipment")
        )
    )


class EquipmentComponentAdminForm(forms.ModelForm):
    class Meta:
        model = EquipmentComponent
        fields = "__all__"

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        is_editing = bool(self.instance.pk and not self.instance._state.adding)
        current_equipment_id = getattr(self.instance, "equipment_id", None) if is_editing else None
        equipment = Equipment.objects.filter(
            warehouse__in=accessible_warehouses(user),
        ).filter(
            ~Q(status=Equipment.Status.RETIRED) | Q(pk=current_equipment_id)
        )
        self.fields["equipment"].queryset = equipment.select_related("warehouse").order_by(
            "warehouse__code", "asset_code"
        )
        set_widget_attr(
            self.fields["equipment"],
            "data-options-url",
            reverse("assets:component-options"),
        )

        equipment_id = self._uuid_or_none(self._selected_id("equipment"))
        selected_equipment = equipment.filter(pk=equipment_id).first() if equipment_id else None
        current_parent_id = getattr(self.instance, "parent_id", None) if is_editing else None
        parents = EquipmentComponent.objects.none()
        if selected_equipment:
            parents = (
                EquipmentComponent.objects.filter(equipment=selected_equipment)
                .filter(
                    Q(status=EquipmentComponent.Status.ACTIVE)
                    | Q(pk=current_parent_id)
                )
                .exclude(pk=self.instance.pk if is_editing else None)
                .order_by("code")
            )

        parent_field = self.fields["parent"]
        parent_field.queryset = parents
        parent_field.empty_label = (
            "请先选择设备" if not selected_equipment else "无上级部件（顶层部件）"
        )
        set_widget_attr(parent_field, "data-dependent-field", "parent")
        if is_editing:
            set_widget_attr(
                parent_field,
                "data-current-component-id",
                str(self.instance.pk),
            )
        if not selected_equipment:
            set_widget_attr(parent_field, "disabled", True)
        else:
            remove_widget_attr(parent_field, "disabled")

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
