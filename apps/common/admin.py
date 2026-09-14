from django.contrib import admin

from .models import Attachment, AuditLog


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "entity_type", "entity_id", "uploaded_by", "created_at")
    search_fields = ("original_name", "entity_type")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "entity_type", "entity_id", "warehouse", "actor")
    list_filter = ("action", "entity_type", "warehouse")
    search_fields = ("request_id", "entity_type", "action")
    readonly_fields = [field.name for field in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

# Register your models here.
