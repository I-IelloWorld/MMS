from .models import Warehouse


def accessible_warehouses(user):
    if not user.is_authenticated:
        return Warehouse.objects.none()
    if user.is_superuser:
        return Warehouse.objects.all()
    return Warehouse.objects.filter(memberships__user=user, memberships__is_active=True).distinct()


def filter_by_warehouse(queryset, user, field_name="warehouse"):
    if user.is_superuser:
        return queryset
    lookup = {f"{field_name}__memberships__user": user, f"{field_name}__memberships__is_active": True}
    return queryset.filter(**lookup).distinct()
