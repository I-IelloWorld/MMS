import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Attachment(TimeStampedModel):
    entity_type = models.CharField("对象类型", max_length=80, db_index=True)
    entity_id = models.UUIDField("对象 ID", db_index=True)
    file = models.FileField("文件", upload_to="attachments/%Y/%m/")
    original_name = models.CharField("原始文件名", max_length=255)
    mime_type = models.CharField("MIME 类型", max_length=120, blank=True)
    size = models.PositiveBigIntegerField("字节数", default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="上传人",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_attachments",
    )

    class Meta:
        verbose_name = "附件"
        verbose_name_plural = "附件"
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return self.original_name


class AuditLog(UUIDModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="操作者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    warehouse = models.ForeignKey(
        "facilities.Warehouse",
        verbose_name="仓库",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField("动作", max_length=80)
    entity_type = models.CharField("对象类型", max_length=80, db_index=True)
    entity_id = models.UUIDField("对象 ID", db_index=True)
    before_data = models.JSONField("变更前", default=dict, blank=True)
    after_data = models.JSONField("变更后", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP 地址", null=True, blank=True)
    request_id = models.CharField("请求 ID", max_length=80, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["warehouse", "created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} {self.action}"

# Create your models here.
