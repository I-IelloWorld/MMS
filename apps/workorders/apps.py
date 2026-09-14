from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkordersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workorders'
    verbose_name = _("维保工单")

    def ready(self):
        from . import signals  # noqa: F401
