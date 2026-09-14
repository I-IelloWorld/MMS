from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.assets.models import AssetCategory, Equipment
from apps.facilities.models import Warehouse, WarehouseMembership, WarehouseRole
from apps.workorders.models import WorkOrder, WorkOrderTask

from .models import Notification, NotificationRecipient


class NotificationLinkTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="notification-engineer",
            email="notification-engineer@example.com",
            password="1",
        )
        role = WarehouseRole.objects.create(
            code="NOTIFY-ENGINEER",
            name="消息测试工程师",
            can_receive_work_orders=True,
        )
        warehouse = Warehouse.objects.create(code="NOTIFY-WH", name="消息测试仓")
        WarehouseMembership.objects.create(
            warehouse=warehouse,
            user=self.user,
            role=role,
        )
        category = AssetCategory.objects.create(code="NOTIFY-CAT", name="消息测试设备")
        equipment = Equipment.objects.create(
            warehouse=warehouse,
            category=category,
            asset_code="NOTIFY-EQ",
            name="消息测试输送线",
        )
        self.work_order = WorkOrder.objects.create(
            number="WO-NOTIFICATION-LINK",
            warehouse=warehouse,
            equipment=equipment,
            title="点击通知进入工单",
            due_at=timezone.now() + timedelta(days=1),
        )

    def _send_to_user(self, notification):
        return NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            channel=NotificationRecipient.Channel.IN_APP,
        )

    def test_work_order_notification_links_to_work_order_detail(self):
        notification = Notification.objects.create(
            notification_type=Notification.Type.WORK_ORDER_CREATED,
            title="新工单",
            message="请处理消息测试工单。",
            entity_type="workorder",
            entity_id=self.work_order.id,
        )
        self._send_to_user(notification)
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'href="{reverse("workorders:detail", args=[self.work_order.id])}"',
        )

    def test_system_notification_is_not_rendered_as_work_order_link(self):
        notification = Notification.objects.create(
            notification_type=Notification.Type.SYSTEM,
            title="系统维护通知",
            message="系统消息没有工单链接。",
        )
        self._send_to_user(notification)
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div class="notification-copy">', html=False)
        self.assertNotContains(response, reverse("workorders:detail", args=[self.work_order.id]))

    def test_deleting_work_order_removes_its_notifications(self):
        notification = Notification.objects.create(
            notification_type=Notification.Type.WORK_ORDER_CREATED,
            title="即将删除的工单",
            message="不应留下失效通知。",
            entity_type="workorder",
            entity_id=self.work_order.id,
        )
        self._send_to_user(notification)

        self.work_order.delete()

        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def test_deleting_order_task_removes_task_notification(self):
        task = WorkOrderTask.objects.create(
            work_order=self.work_order,
            sequence=1,
            title="即将删除的任务",
        )
        notification = Notification.objects.create(
            notification_type=Notification.Type.SYSTEM,
            title="工单任务提醒",
            message="任务提醒不应在任务删除后保留。",
            entity_type="workordertask",
            entity_id=task.id,
        )
        self._send_to_user(notification)

        task.delete()

        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

# Create your tests here.
