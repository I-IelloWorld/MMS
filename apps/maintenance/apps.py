from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    """Migration history only; no runtime models, tables, views or permissions."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.maintenance'
    verbose_name = 'Retired maintenance migrations'
