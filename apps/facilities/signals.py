from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .models import WarehouseMembership, WarehouseRole


def _enable_staff(user):
    if not user.is_staff:
        type(user).objects.filter(pk=user.pk).update(is_staff=True)
        user.is_staff = True


@receiver(post_save, sender=WarehouseMembership)
def enable_admin_access_for_role_member(sender, instance, **kwargs):
    if instance.is_active and instance.role.is_active and instance.role.permissions.exists():
        _enable_staff(instance.user)


@receiver(m2m_changed, sender=WarehouseRole.permissions.through)
def enable_admin_access_when_role_gets_permissions(sender, instance, action, **kwargs):
    if action == "post_add":
        for membership in instance.memberships.filter(is_active=True).select_related("user"):
            _enable_staff(membership.user)
