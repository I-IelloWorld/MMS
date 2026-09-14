from apps.facilities.access import accessible_warehouses
from apps.notifications.models import NotificationRecipient


def workspace_context(request):
    if not request.user.is_authenticated:
        return {"nav_warehouses": [], "unread_notification_count": 0}
    return {
        "nav_warehouses": accessible_warehouses(request.user)[:8],
        "unread_notification_count": NotificationRecipient.objects.filter(
            user=request.user,
            channel=NotificationRecipient.Channel.IN_APP,
            read_at__isnull=True,
        ).count(),
    }
