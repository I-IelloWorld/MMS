import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.timezones import DEFAULT_TIMEZONE, US_TIMEZONE_CHOICES


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("邮箱"), unique=True)
    display_name = models.CharField(_("姓名"), max_length=100, blank=True)
    phone = models.CharField(_("电话"), max_length=32, blank=True)
    timezone = models.CharField(
        _("时区"),
        max_length=64,
        choices=US_TIMEZONE_CHOICES,
        default=DEFAULT_TIMEZONE,
    )

    class Meta:
        verbose_name = _("用户")
        verbose_name_plural = _("用户")

    def __str__(self):
        return self.display_name or self.get_full_name() or self.username

# Create your models here.
