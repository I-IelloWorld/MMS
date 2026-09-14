from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DataImportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_imports'
    verbose_name = _("数据导入")
