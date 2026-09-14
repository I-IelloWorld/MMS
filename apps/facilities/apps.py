from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FacilitiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.facilities'
    verbose_name = _("仓库组织")

    def ready(self):
        from . import signals  # noqa: F401
