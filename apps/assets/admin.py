from django.contrib import admin

from apps.common.admin_mixins import RequestUserFormMixin

from .forms import EquipmentComponentAdminForm
from .models import AssetCategory, Equipment, EquipmentComponent


class EquipmentComponentInline(admin.TabularInline):
    model = EquipmentComponent
    extra = 0
    fields = ("code", "name", "component_type", "status")


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "name", "warehouse", "category", "criticality", "status")
    list_filter = ("warehouse", "category", "criticality", "status")
    search_fields = ("asset_code", "name", "serial_number", "manufacturer", "model")
    inlines = (EquipmentComponentInline,)


@admin.register(EquipmentComponent)
class EquipmentComponentAdmin(RequestUserFormMixin, admin.ModelAdmin):
    form = EquipmentComponentAdminForm
    list_display = ("code", "name", "equipment", "component_type", "status")
    list_filter = ("status", "component_type")
    search_fields = ("code", "name", "equipment__asset_code")

    class Media:
        js = ("js/equipment-component-dependent-selects.js",)

# Register your models here.
