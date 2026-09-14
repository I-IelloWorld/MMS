from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        WORK_ORDER_CREATED = "WORK_ORDER_CREATED", _("新工单")
        WORK_ORDER_DUE = "WORK_ORDER_DUE", _("工单到期提醒")
        WORK_ORDER_OVERDUE = "WORK_ORDER_OVERDUE", _("工单逾期")
        SYSTEM = "SYSTEM", _("系统消息")

    notification_type = models.CharField(_("通知类型"), max_length=32, choices=Type.choices)
    title = models.CharField(_("标题"), max_length=180)
    message = models.TextField(_("消息内容"))
    entity_type = models.CharField(_("对象类型"), max_length=80, blank=True)
    entity_id = models.UUIDField(_("对象 ID"), null=True, blank=True)
    dedup_key = models.CharField(_("幂等键"), max_length=160, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = _("通知")
        verbose_name_plural = _("通知")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return self.title


class NotificationRecipient(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "IN_APP", _("站内")
        EMAIL = "EMAIL", _("邮件")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("待发送")
        SENT = "SENT", _("已发送")
        FAILED = "FAILED", _("失败")

    notification = models.ForeignKey(Notification, verbose_name=_("通知"), on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("接收人"), on_delete=models.CASCADE, related_name="notification_recipients")
    channel = models.CharField(_("渠道"), max_length=16, choices=Channel.choices, default=Channel.IN_APP)
    status = models.CharField(_("发送状态"), max_length=16, choices=Status.choices, default=Status.SENT, db_index=True)
    sent_at = models.DateTimeField(_("发送时间"), null=True, blank=True)
    read_at = models.DateTimeField(_("已读时间"), null=True, blank=True)
    error_message = models.TextField(_("失败原因"), blank=True)
    retry_count = models.PositiveIntegerField(_("重试次数"), default=0)

    class Meta:
        verbose_name = _("通知接收记录")
        verbose_name_plural = _("通知接收记录")
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["notification", "user", "channel"], name="uniq_notification_user_channel")]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self):
        return f"{self.user} / {self.notification.title}"

# Create your models here.
