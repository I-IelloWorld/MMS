def can_manage_work_orders(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("workorders.modify_workorder"):
        return True
    return user.warehouse_memberships.filter(
        is_active=True,
        role__is_active=True,
        role__can_manage_work_orders=True,
    ).exists()
