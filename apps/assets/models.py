from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class AssetCategory(TimeStampedModel):
    code = models.CharField(_("分类编码"), max_length=40, unique=True)
    name = models.CharField(_("分类名称"), max_length=100)
    parent = models.ForeignKey("self", verbose_name=_("上级分类"), on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    is_active = models.BooleanField(_("有效"), default=True)

    class Meta:
        verbose_name = _("设备分类")
        verbose_name_plural = _("设备分类")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class Equipment(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("投产")
        INACTIVE = "INACTIVE", _("停用")
        TRIAL = "TRIAL", _("试运行")
        COMMISSIONING = "COMMISSIONING", _("调试")
        RETIRED = "RETIRED", _("废弃")

    class Criticality(models.TextChoices):
        LOW = "LOW", _("低")
        MEDIUM = "MEDIUM", _("中")
        HIGH = "HIGH", _("高")
        CRITICAL = "CRITICAL", _("关键")

    warehouse = models.ForeignKey("facilities.Warehouse", verbose_name=_("仓库"), on_delete=models.PROTECT, related_name="equipment")
    category = models.ForeignKey(AssetCategory, verbose_name=_("设备分类"), on_delete=models.PROTECT, related_name="equipment")
    asset_code = models.CharField(_("设备编码"), max_length=64)
    name = models.CharField(_("设备名称"), max_length=120)
    manufacturer = models.CharField(_("制造商"), max_length=120, blank=True)
    model = models.CharField(_("型号"), max_length=120, blank=True)
    serial_number = models.CharField(_("序列号"), max_length=120, blank=True)
    commissioned_on = models.DateField(_("投产日期"), null=True, blank=True)
    location_detail = models.CharField(_("位置"), max_length=255, blank=True)
    criticality = models.CharField(_("关键度"), max_length=16, choices=Criticality.choices, default=Criticality.MEDIUM, db_index=True)
    status = models.CharField(_("状态"), max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    metadata = models.JSONField(_("扩展属性"), default=dict, blank=True)

    class Meta:
        verbose_name = _("自动化设备")
        verbose_name_plural = _("自动化设备")
        ordering = ["warehouse__code", "asset_code"]
        constraints = [models.UniqueConstraint(fields=["warehouse", "asset_code"], name="uniq_asset_code_per_warehouse")]
        indexes = [models.Index(fields=["warehouse", "status", "criticality"])]

    def __str__(self):
        return f"{self.asset_code} · {self.name}"


class EquipmentComponent(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("启用")
        INACTIVE = "INACTIVE", _("停用")

    equipment = models.ForeignKey(Equipment, verbose_name=_("设备"), on_delete=models.CASCADE, related_name="components")
    parent = models.ForeignKey("self", verbose_name=_("上级部件"), on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    code = models.CharField(_("部件编码"), max_length=64)
    name = models.CharField(_("部件名称"), max_length=120)
    component_type = models.CharField(_("部件类型"), max_length=80, blank=True)
    serial_number = models.CharField(_("序列号"), max_length=120, blank=True)
    status = models.CharField(_("状态"), max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name = _("设备部件")
        verbose_name_plural = _("设备部件")
        ordering = ["equipment", "code"]
        constraints = [models.UniqueConstraint(fields=["equipment", "code"], name="uniq_component_code_per_equipment")]

    def clean(self):
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError({"parent": "部件不能以自身作为上级部件。"})
        if self.parent_id and self.parent.equipment_id != self.equipment_id:
            raise ValidationError({"parent": "上级部件必须属于同一设备。"})

    def __str__(self):
        return f"{self.equipment.asset_code} / {self.code} · {self.name}"

# Create your models here.
