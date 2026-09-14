from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q


MODIFY_ACTIONS = ("add", "change", "delete")


def permission_alias(permission_name):
    """Map Django's three write checks to one explicit modify permission."""
    try:
        app_label, codename = permission_name.split(".", 1)
        action, model_name = codename.split("_", 1)
    except ValueError:
        return None
    if action not in MODIFY_ACTIONS:
        return None
    return f"{app_label}.modify_{model_name}"


def selectable_permissions():
    """Permissions shown in user, group, and warehouse-role admin forms."""
    available = Q(pk__in=[])
    for model in admin.site._registry:
        available |= Q(
            content_type__app_label=model._meta.app_label,
            content_type__model=model._meta.model_name,
        )
    return Permission.objects.filter(
        available,
    ).filter(
        Q(codename__startswith="view_") | Q(codename__startswith="modify_")
    ).select_related("content_type")


def ensure_modify_permissions(app_config, using="default"):
    """Keep two permissions per live model and preserve existing write grants."""
    permission_manager = Permission.objects.db_manager(using)
    role_model = apps.get_model("facilities", "WarehouseRole")
    grant_tables = (
        (get_user_model().user_permissions.through, "user_id"),
        (Group.permissions.through, "group_id"),
        (role_model.permissions.through, "warehouserole_id"),
    )
    with transaction.atomic(using=using):
        for model in app_config.get_models():
            content_type = ContentType.objects.db_manager(using).get_for_model(model)
            modify, _ = permission_manager.get_or_create(
                content_type=content_type,
                codename=f"modify_{content_type.model}",
                defaults={"name": f"Can modify {model._meta.verbose_name_raw}"},
            )
            legacy = permission_manager.filter(
                content_type=content_type,
                codename__in=[f"{action}_{content_type.model}" for action in MODIFY_ACTIONS],
            )
            for through, owner_field in grant_tables:
                grants = through.objects.using(using)
                owner_ids = grants.filter(permission__in=legacy).values_list(owner_field, flat=True).distinct()
                grants.bulk_create(
                    [through(**{owner_field: pk, "permission_id": modify.pk}) for pk in owner_ids],
                    ignore_conflicts=True,
                )
            legacy.delete()
