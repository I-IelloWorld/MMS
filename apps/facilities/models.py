from django.conf import settings
from django.contrib.auth.models import Permission
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel
from apps.common.timezones import DEFAULT_TIMEZONE, US_TIMEZONE_CHOICES


class Warehouse(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("启用")
        INACTIVE = "INACTIVE", _("停用")

    code = models.CharField(_("仓库编码"), max_length=32, unique=True)
    name = models.CharField(_("仓库名称"), max_length=120)
    address = models.TextField(_("地址"), blank=True)
    timezone = models.CharField(
        _("时区"),
        max_length=64,
        choices=US_TIMEZONE_CHOICES,
        default=DEFAULT_TIMEZONE,
    )
    status = models.CharField(_("状态"), max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        verbose_name = _("仓库")
        verbose_name_plural = _("仓库")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class WarehouseRole(TimeStampedModel):
    code = models.CharField(_("角色编码"), max_length=32, unique=True)
    name = models.CharField(_("角色名称"), max_length=80)
    description = models.TextField(_("角色说明"), blank=True)
    can_receive_work_orders = models.BooleanField(_("可接收工单"), default=False)
    can_manage_work_orders = models.BooleanField(_("可管理工单"), default=False)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("系统权限"),
        blank=True,
        help_text=_("角色成员可获得的 Django 系统权限。"),
    )
    is_active = models.BooleanField(_("有效"), default=True)

    class Meta:
        verbose_name = _("仓库角色")
        verbose_name_plural = _("仓库角色")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class WarehouseMembership(TimeStampedModel):
    # Kept as constants so integrations can refer to the seeded role codes.
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "仓库管理员"
        ENGINEER = "ENGINEER", "自动化工程师"
        SUPERVISOR = "SUPERVISOR", "维保主管"
        VIEWER = "VIEWER", "只读/审计"

    warehouse = models.ForeignKey(Warehouse, verbose_name=_("仓库"), on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("用户"), on_delete=models.CASCADE, related_name="warehouse_memberships")
    role = models.ForeignKey(
        WarehouseRole,
        verbose_name=_("角色"),
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    is_primary = models.BooleanField(_("主要仓库"), default=False)
    notification_enabled = models.BooleanField(_("接收通知"), default=True)
    is_active = models.BooleanField(_("有效"), default=True)

    class Meta:
        verbose_name = _("仓库成员")
        verbose_name_plural = _("仓库成员")
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "user"], name="uniq_warehouse_user_membership"),
            models.UniqueConstraint(fields=["user"], condition=Q(is_primary=True), name="uniq_primary_warehouse_per_user"),
        ]

    def __str__(self):
        return f"{self.warehouse.code} / {self.user} / {self.role.name}"

    def get_role_display(self):
        return self.role.name

# Create your models here.
