from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from .models import User
from .permissions import selectable_permissions


class ConsolidatedUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "user_permissions" in self.fields:
            self.fields["user_permissions"].queryset = selectable_permissions()


class ConsolidatedGroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = selectable_permissions()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    form = ConsolidatedUserChangeForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("个人信息"), {"fields": ("display_name", "email", "phone", "timezone")}),
        (
            _("权限"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("重要日期"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
        (_("个人信息"), {"fields": ("display_name", "email", "phone")}),
    )
    list_display = ("username", "display_name", "email", "is_active", "is_staff")
    search_fields = ("username", "display_name", "email")

    @staticmethod
    def _is_protected_admin(obj):
        return bool(obj and obj.username == "admin")

    def get_fieldsets(self, request, obj=None):
        if self._is_protected_admin(obj):
            return (
                (None, {"fields": ("username",)}),
                (_("个人信息"), {"fields": ("display_name", "email", "phone", "timezone")}),
                (
                    _("权限"),
                    {
                        "fields": (
                            "is_active",
                            "is_staff",
                            "is_superuser",
                            "groups",
                            "user_permissions",
                        )
                    },
                ),
                (_("重要日期"), {"fields": ("last_login", "date_joined")}),
            )
        return super().get_fieldsets(request, obj=obj)

    def has_change_permission(self, request, obj=None):
        if self._is_protected_admin(obj):
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_protected_admin(obj):
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_model(self, request, obj):
        if self._is_protected_admin(obj):
            raise PermissionDenied(_("admin 账号只能查看，不能删除。"))
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(username="admin").exists():
            raise PermissionDenied(_("admin 账号只能查看，不能删除。"))
        return super().delete_queryset(request, queryset)


admin.site.unregister(Group)


@admin.register(Group)
class ConsolidatedGroupAdmin(GroupAdmin):
    form = ConsolidatedGroupForm

# Register your models here.
