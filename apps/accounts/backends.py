from django.contrib.auth.backends import ModelBackend

from .permissions import permission_alias


class WarehouseRoleBackend(ModelBackend):
    """Include permissions configured on active warehouse roles."""

    def get_group_permissions(self, user_obj, obj=None):
        permissions = super().get_group_permissions(user_obj, obj=obj)
        if obj is not None or not user_obj.is_active or user_obj.is_anonymous:
            return permissions
        role_permissions = user_obj.warehouse_memberships.filter(
            is_active=True,
            role__is_active=True,
        ).values_list(
            "role__permissions__content_type__app_label",
            "role__permissions__codename",
        )
        return permissions | {
            f"{app_label}.{codename}"
            for app_label, codename in role_permissions
            if app_label and codename
        }

    def has_perm(self, user_obj, perm, obj=None):
        if super().has_perm(user_obj, perm, obj=obj):
            return True
        alias = permission_alias(perm)
        return bool(alias and super().has_perm(user_obj, alias, obj=obj))
