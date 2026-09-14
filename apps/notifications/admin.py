from django.contrib import admin

from .models import Notification, NotificationRecipient


class NotificationRecipientInline(admin.TabularInline):
    model = NotificationRecipient
    extra = 0


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "notification_type", "entity_type", "created_at")
    list_filter = ("notification_type",)
    search_fields = ("title", "message", "dedup_key")
    inlines = (NotificationRecipientInline,)


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "channel", "status", "sent_at", "read_at")
    list_filter = ("channel", "status")
    search_fields = ("notification__title", "user__username", "user__display_name")

# Register your models here.
