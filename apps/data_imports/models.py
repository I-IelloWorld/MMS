from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class ImportBatch(TimeStampedModel):
    class ImportType(models.TextChoices):
        EQUIPMENT = "EQUIPMENT", _("设备与部件")

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", _("已上传")
        VALIDATING = "VALIDATING", _("校验中")
        READY = "READY", _("待执行")
        RUNNING = "RUNNING", _("导入中")
        COMPLETED = "COMPLETED", _("已完成")
        FAILED = "FAILED", _("失败")

    warehouse = models.ForeignKey("facilities.Warehouse", verbose_name=_("目标仓库"), on_delete=models.PROTECT, related_name="import_batches")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("创建人"), on_delete=models.PROTECT, related_name="import_batches")
    source_file = models.FileField(_("源文件"), upload_to="imports/%Y/%m/")
    import_type = models.CharField(_("导入类型"), max_length=20, choices=ImportType.choices, default=ImportType.EQUIPMENT)
    status = models.CharField(_("状态"), max_length=20, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    total_rows = models.PositiveIntegerField(_("总行数"), default=0)
    success_rows = models.PositiveIntegerField(_("成功行数"), default=0)
    failed_rows = models.PositiveIntegerField(_("失败行数"), default=0)
    started_at = models.DateTimeField(_("开始时间"), null=True, blank=True)
    finished_at = models.DateTimeField(_("结束时间"), null=True, blank=True)

    class Meta:
        verbose_name = _("导入批次")
        verbose_name_plural = _("导入批次")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.warehouse.code} / {self.get_import_type_display()} / {self.created_at:%Y-%m-%d %H:%M}"


class ImportError(TimeStampedModel):
    batch = models.ForeignKey(ImportBatch, verbose_name=_("导入批次"), on_delete=models.CASCADE, related_name="errors")
    row_number = models.PositiveIntegerField(_("行号"))
    field_name = models.CharField(_("字段"), max_length=80, blank=True)
    error_code = models.CharField(_("错误代码"), max_length=80)
    error_message = models.TextField(_("错误说明"))
    raw_data = models.JSONField(_("原始数据"), default=dict, blank=True)

    class Meta:
        verbose_name = _("导入错误")
        verbose_name_plural = _("导入错误")
        ordering = ["batch", "row_number"]
        indexes = [models.Index(fields=["batch", "row_number"])]

    def __str__(self):
        return f"第 {self.row_number} 行：{self.error_message}"

# Create your models here.
