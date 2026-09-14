from django.contrib import admin

from .models import ImportBatch, ImportError


class ImportErrorInline(admin.TabularInline):
    model = ImportError
    extra = 0
    readonly_fields = ("row_number", "field_name", "error_code", "error_message", "raw_data")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "import_type", "status", "total_rows", "success_rows", "failed_rows", "created_by", "created_at")
    list_filter = ("warehouse", "import_type", "status")
    inlines = (ImportErrorInline,)


admin.site.register(ImportError)

# Register your models here.
