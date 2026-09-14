from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.accounts.permissions import selectable_permissions

from .models import Warehouse, WarehouseMembership, WarehouseRole


class WarehouseMembershipInline(admin.TabularInline):
    model = WarehouseMembership
    extra = 0


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "timezone", "status")
    list_filter = ("status", "timezone")
    search_fields = ("code", "name", "address")
    inlines = (WarehouseMembershipInline,)


@admin.register(WarehouseMembership)
class WarehouseMembershipAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "user", "role", "is_primary", "notification_enabled", "is_active")
    list_filter = ("role", "is_primary", "notification_enabled", "is_active")
    search_fields = ("warehouse__code", "warehouse__name", "user__username", "user__display_name")


@admin.register(WarehouseRole)
class WarehouseRoleAdmin(admin.ModelAdmin):
    class WarehouseRoleAdminForm(forms.ModelForm):
        class Meta:
            model = WarehouseRole
            fields = "__all__"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            permissions = self.fields["permissions"]
            permissions.queryset = selectable_permissions()
            permissions.help_text = _(
                "每个数据类型仅提供 view（查看）和 modify（新增、修改、删除）两种权限。"
            )

    form = WarehouseRoleAdminForm
    list_display = ("code", "name", "can_receive_work_orders", "can_manage_work_orders", "is_active")
    list_filter = ("can_receive_work_orders", "can_manage_work_orders", "is_active")
    search_fields = ("code", "name", "description")
    filter_horizontal = ("permissions",)

# Register your models here.
