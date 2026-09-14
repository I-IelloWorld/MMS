from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_migrate
from django.dispatch import receiver

from .permissions import ensure_modify_permissions


def _clear_permission_cache(user):
    for cache_name in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
        user.__dict__.pop(cache_name, None)


@receiver(m2m_changed, sender=get_user_model().groups.through)
def enable_admin_access_for_group_members(sender, instance, action, **kwargs):
    """Group permissions only appear in Django Admin when the user is staff."""
    if action in {"post_add", "post_remove", "post_clear"}:
        _clear_permission_cache(instance)
    if action == "post_add" and instance.groups.exists():
        if not instance.is_staff:
            type(instance).objects.filter(pk=instance.pk).update(is_staff=True)
            instance.is_staff = True


@receiver(post_migrate, dispatch_uid="accounts.ensure_modify_permissions")
def create_modify_permissions(sender, using, **kwargs):
    ensure_modify_permissions(sender, using=using)
