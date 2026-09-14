from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.assets.models import AssetCategory, Equipment, EquipmentComponent
from apps.facilities.models import Warehouse, WarehouseMembership, WarehouseRole
from apps.notifications.models import NotificationRecipient

from .forms import WORK_ORDER_INPUT_FIELDS, WorkOrderAdminForm, WorkOrderCreateForm
from .models import WorkOrder, WorkOrderTask
from .services import complete_work_order_task, generate_recurring_work_orders


class WorkOrderSchedulingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.engineer = user_model.objects.create_user(
            username="workorder-engineer",
            email="workorder-engineer@example.com",
            password="1",
            display_name="一仓工程师",
        )
        self.supervisor = user_model.objects.create_user(
            username="workorder-supervisor",
            email="workorder-supervisor@example.com",
            password="1",
            display_name="一仓主管",
        )
        self.viewer = user_model.objects.create_user(
            username="workorder-viewer",
            email="workorder-viewer@example.com",
            password="1",
        )
        self.other_engineer = user_model.objects.create_user(
            username="other-workorder-engineer",
            email="other-workorder-engineer@example.com",
            password="1",
        )
        self.engineer_role = WarehouseRole.objects.create(
            code="WO-ENGINEER",
            name="自动化工程师",
            can_receive_work_orders=True,
        )
        self.supervisor_role = WarehouseRole.objects.create(
            code="WO-SUPERVISOR",
            name="维保主管",
            can_receive_work_orders=True,
            can_manage_work_orders=True,
        )
        self.viewer_role = WarehouseRole.objects.create(code="WO-VIEWER", name="只读")
        self.warehouse = Warehouse.objects.create(code="WO-A", name="工单一仓")
        self.other_warehouse = Warehouse.objects.create(code="WO-B", name="工单二仓")
        WarehouseMembership.objects.create(
            warehouse=self.warehouse,
            user=self.engineer,
            role=self.engineer_role,
        )
        WarehouseMembership.objects.create(
            warehouse=self.warehouse,
            user=self.supervisor,
            role=self.supervisor_role,
        )
        WarehouseMembership.objects.create(
            warehouse=self.warehouse,
            user=self.viewer,
            role=self.viewer_role,
        )
        WarehouseMembership.objects.create(
            warehouse=self.other_warehouse,
            user=self.other_engineer,
            role=self.engineer_role,
        )
        category = AssetCategory.objects.create(code="WO-CAT", name="工单测试设备")
        self.equipment = Equipment.objects.create(
            warehouse=self.warehouse,
            category=category,
            asset_code="WO-EQ-A",
            name="一仓设备",
        )
        self.other_equipment = Equipment.objects.create(
            warehouse=self.other_warehouse,
            category=category,
            asset_code="WO-EQ-B",
            name="二仓设备",
        )
        self.component = EquipmentComponent.objects.create(
            equipment=self.equipment,
            code="WO-COMP-A",
            name="一仓部件",
        )
        self.other_component = EquipmentComponent.objects.create(
            equipment=self.other_equipment,
            code="WO-COMP-B",
            name="二仓部件",
        )

    def _valid_form_data(self, schedule_type=WorkOrder.ScheduleType.RECURRING):
        due_at = timezone.now() + timedelta(days=1)
        return {
            "schedule_type": schedule_type,
            "warehouse": self.warehouse.id,
            "equipment": self.equipment.id,
            "component": self.component.id,
            "title": "一仓设备维保",
            "description": "检查设备",
            "work_type": WorkOrder.Type.PREVENTIVE,
            "priority": WorkOrder.Priority.MEDIUM,
            "timezone": "America/Chicago",
            "due_at": due_at.strftime("%Y-%m-%dT%H:%M"),
            "task_duration_hours": 8,
            "recurrence_unit": WorkOrder.CycleUnit.MONTH if schedule_type == WorkOrder.ScheduleType.RECURRING else "",
            "recurrence_interval": 1,
            "recurrence_end_at": "",
            "assignee": self.engineer.id,
        }

    def test_unbound_form_disables_dependent_fields(self):
        form = WorkOrderCreateForm(user=self.engineer)

        for field_name in ("equipment", "component", "assignee"):
            self.assertIn("disabled", form.fields[field_name].widget.attrs)
            self.assertFalse(form.fields[field_name].queryset.exists())

    def test_recurring_form_scopes_relations_and_sets_next_occurrence(self):
        form = WorkOrderCreateForm(data=self._valid_form_data(), user=self.engineer)

        self.assertTrue(form.is_valid(), form.errors)
        work_order = form.save(commit=False)
        self.assertEqual(work_order.schedule_type, WorkOrder.ScheduleType.RECURRING)
        self.assertTrue(work_order.recurrence_active)
        self.assertEqual(work_order.recurrence_number, 1)
        self.assertGreater(work_order.next_occurrence_at, work_order.due_at)
        self.assertEqual(work_order.task_duration_hours, 8)
        self.assertQuerySetEqual(form.fields["equipment"].queryset, [self.equipment])
        self.assertQuerySetEqual(form.fields["component"].queryset, [self.component])
        self.assertQuerySetEqual(
            form.fields["assignee"].queryset,
            [self.engineer, self.supervisor],
            ordered=False,
        )

    def test_one_time_form_clears_recurrence_fields(self):
        form = WorkOrderCreateForm(
            data=self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME),
            user=self.engineer,
        )

        self.assertTrue(form.is_valid(), form.errors)
        work_order = form.save(commit=False)
        self.assertFalse(work_order.recurrence_active)
        self.assertIsNone(work_order.next_occurrence_at)
        self.assertEqual(work_order.recurrence_unit, "")

    def test_one_time_form_accepts_browser_post_without_disabled_recurrence_fields(self):
        data = self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME)
        for field_name in (
            "recurrence_unit",
            "recurrence_interval",
            "recurrence_end_at",
        ):
            data.pop(field_name)

        form = WorkOrderCreateForm(data=data, user=self.engineer)

        self.assertTrue(form.is_valid(), form.errors)
        work_order = form.save(commit=False)
        self.assertEqual(work_order.recurrence_interval, 1)
        self.assertFalse(work_order.recurrence_active)

    def test_create_page_creates_direct_work_order(self):
        self.client.force_login(self.supervisor)

        response = self.client.post(reverse("workorders:create"), self._valid_form_data())

        self.assertEqual(response.status_code, 302)
        work_order = WorkOrder.objects.get(title="一仓设备维保")
        self.assertEqual(work_order.created_by, self.supervisor)
        self.assertEqual(work_order.status, WorkOrder.Status.ASSIGNED)
        self.assertTrue(work_order.recurrence_active)

    def test_create_page_creates_one_time_order_without_recurrence_post_data(self):
        self.client.force_login(self.supervisor)
        data = self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME)
        data["title"] = "一次性浏览器工单"
        for field_name in (
            "recurrence_unit",
            "recurrence_interval",
            "recurrence_end_at",
        ):
            data.pop(field_name)

        response = self.client.post(reverse("workorders:create"), data)

        self.assertEqual(response.status_code, 302)
        work_order = WorkOrder.objects.get(title="一次性浏览器工单")
        self.assertEqual(work_order.schedule_type, WorkOrder.ScheduleType.ONE_TIME)
        self.assertEqual(work_order.recurrence_interval, 1)
        self.assertFalse(work_order.recurrence_active)

    def test_non_manager_cannot_open_create_page_or_see_create_buttons(self):
        self.client.force_login(self.engineer)

        create_response = self.client.get(reverse("workorders:create"))
        dashboard_response = self.client.get(reverse("dashboard:home"))
        list_response = self.client.get(reverse("workorders:list"))

        self.assertEqual(create_response.status_code, 403)
        create_url = reverse("workorders:create")
        self.assertNotContains(dashboard_response, f'href="{create_url}"')
        self.assertNotContains(list_response, f'href="{create_url}"')

    def test_create_page_can_add_optional_order_tasks(self):
        self.client.force_login(self.supervisor)
        data = self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME)
        data.update(
            {
                "title": "带任务的一次性工单",
                "tasks-TOTAL_FORMS": "2",
                "tasks-INITIAL_FORMS": "0",
                "tasks-MIN_NUM_FORMS": "0",
                "tasks-MAX_NUM_FORMS": "1000",
                "tasks-0-title": "检查传感器",
                "tasks-0-instructions": "确认读数稳定",
                "tasks-0-requires_photo": "on",
                "tasks-1-title": "清洁镜头",
                "tasks-1-instructions": "",
            }
        )

        response = self.client.post(reverse("workorders:create"), data)

        self.assertEqual(response.status_code, 302)
        order = WorkOrder.objects.get(title="带任务的一次性工单")
        self.assertEqual(
            list(order.tasks.values_list("sequence", "title", "requires_photo")),
            [(1, "检查传感器", True), (2, "清洁镜头", False)],
        )

    def test_photo_required_task_cannot_complete_without_photo(self):
        order = WorkOrder.objects.create(
            number="WO-PHOTO-REQUIRED",
            warehouse=self.warehouse,
            equipment=self.equipment,
            title="拍照确认",
            due_at=timezone.now(),
            status=WorkOrder.Status.IN_PROGRESS,
            assignee=self.engineer,
        )
        task = WorkOrderTask.objects.create(
            work_order=order,
            sequence=1,
            title="上传现场照片",
            requires_photo=True,
        )

        with self.assertRaises(ValidationError):
            complete_work_order_task(task.id, self.engineer, "无照片")

        photo = SimpleUploadedFile(
            "现场.jpg",
            b"test-image-content",
            content_type="image/jpeg",
        )
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            complete_work_order_task(task.id, self.engineer, "照片已上传", photo)
            task.refresh_from_db()
            self.assertEqual(task.status, WorkOrderTask.Status.DONE)
            self.assertTrue(task.photo.name.endswith(".jpg"))

    def test_overdue_starts_after_generation_time_plus_task_duration(self):
        now = timezone.now()
        work_order = WorkOrder.objects.create(
            number="WO-DURATION-001",
            warehouse=self.warehouse,
            equipment=self.equipment,
            title="任务时间测试",
            due_at=now - timedelta(hours=2),
            task_duration_hours=3,
        )

        with patch("django.utils.timezone.now", return_value=now):
            self.assertFalse(work_order.is_overdue)
            self.assertEqual(work_order.remaining_hours, 1)
            self.assertEqual(
                work_order.deadline_at,
                work_order.due_at + timedelta(hours=3),
            )

        work_order.due_at = now - timedelta(hours=4)
        with patch("django.utils.timezone.now", return_value=now):
            self.assertTrue(work_order.is_overdue)
            self.assertEqual(work_order.remaining_hours, 0)

    def test_forged_cross_warehouse_relations_are_rejected(self):
        data = self._valid_form_data()
        data.update(
            {
                "equipment": self.other_equipment.id,
                "component": self.other_component.id,
                "assignee": self.other_engineer.id,
            }
        )
        form = WorkOrderCreateForm(data=data, user=self.engineer)
        forged_order = WorkOrder(
            number="WO-FORGED-001",
            warehouse=self.warehouse,
            equipment=self.other_equipment,
            component=self.other_component,
            title="伪造工单",
            due_at=timezone.now() + timedelta(days=1),
            assignee=self.other_engineer,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("equipment", form.errors)
        self.assertIn("component", form.errors)
        self.assertIn("assignee", form.errors)
        with self.assertRaises(ValidationError):
            forged_order.full_clean()

    def test_options_endpoint_returns_only_related_and_authorized_records(self):
        self.client.force_login(self.engineer)
        response = self.client.get(
            reverse("workorders:options"),
            {"warehouse": self.warehouse.id, "equipment": self.equipment.id},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual({item["value"] for item in data["equipment"]}, {str(self.equipment.id)})
        self.assertEqual({item["value"] for item in data["components"]}, {str(self.component.id)})
        self.assertEqual(
            {item["value"] for item in data["assignees"]},
            {str(self.engineer.id), str(self.supervisor.id)},
        )

    def test_recurring_generator_clones_order_tasks_and_notifies_assignee(self):
        form = WorkOrderCreateForm(data=self._valid_form_data(), user=self.engineer)
        self.assertTrue(form.is_valid(), form.errors)
        source = form.save(commit=False)
        source.number = "WO-RECURRING-001"
        source.status = WorkOrder.Status.ASSIGNED
        source.next_occurrence_at = timezone.now() - timedelta(minutes=1)
        source.save()
        WorkOrderTask.objects.create(work_order=source, sequence=1, title="检查传感器")

        created = generate_recurring_work_orders()

        self.assertEqual(len(created), 1)
        occurrence = created[0]
        self.assertEqual(occurrence.recurrence_source, source)
        self.assertEqual(occurrence.schedule_type, WorkOrder.ScheduleType.ONE_TIME)
        self.assertEqual(occurrence.task_duration_hours, 8)
        self.assertEqual(occurrence.tasks.get().title, "检查传感器")
        self.assertTrue(
            NotificationRecipient.objects.filter(
                notification__entity_id=occurrence.id,
                user=self.engineer,
            ).exists()
        )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_public_and_admin_pages_load_current_form_script(self):
        administrator = get_user_model().objects.create_superuser(
            username="workorder-admin",
            email="workorder-admin@example.com",
            password="1",
        )
        self.client.force_login(administrator)

        public_response = self.client.get(reverse("workorders:create"))
        admin_response = self.client.get(reverse("admin:workorders_workorder_add"))

        self.assertContains(public_response, "js/work-order-form.js")
        self.assertContains(admin_response, "js/work-order-form.js")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_admin_add_uses_public_business_fields_and_system_defaults(self):
        administrator = get_user_model().objects.create_superuser(
            username="workorder-create-admin",
            email="workorder-create-admin@example.com",
            password="1",
        )
        self.client.force_login(administrator)

        add_response = self.client.get(reverse("admin:workorders_workorder_add"))
        add_fields = set(add_response.context["adminform"].form.fields)
        self.assertEqual(add_fields, set(WORK_ORDER_INPUT_FIELDS))
        self.assertNotIn("number", add_fields)
        self.assertNotIn("status", add_fields)
        self.assertNotIn("created_by", add_fields)

        data = self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME)
        data["title"] = "后台一次性工单"
        data.update(
            {
                "tasks-TOTAL_FORMS": "1",
                "tasks-INITIAL_FORMS": "0",
                "tasks-MIN_NUM_FORMS": "0",
                "tasks-MAX_NUM_FORMS": "1000",
            }
        )
        for field_name in (
            "recurrence_unit",
            "recurrence_interval",
            "recurrence_end_at",
        ):
            data.pop(field_name)

        response = self.client.post(reverse("admin:workorders_workorder_add"), data)

        self.assertEqual(
            response.status_code,
            302,
            [
                formset.formset.errors
                for formset in response.context.get("inline_admin_formsets", [])
            ]
            if response.context
            else None,
        )
        work_order = WorkOrder.objects.get(title="后台一次性工单")
        self.assertTrue(work_order.number.startswith("WO-"))
        self.assertEqual(work_order.created_by, administrator)
        self.assertEqual(work_order.status, WorkOrder.Status.ASSIGNED)
        self.assertFalse(work_order.recurrence_active)

    def test_create_page_shows_generation_start_label_and_error_summary(self):
        self.client.force_login(self.supervisor)
        data = self._valid_form_data(WorkOrder.ScheduleType.ONE_TIME)
        data["title"] = ""
        data.pop("recurrence_interval")

        response = self.client.post(reverse("workorders:create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "工单未创建，请检查以下字段")
        self.assertContains(response, "工单开始生成日期")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_spanish_create_page_translates_form_and_dependency_labels(self):
        self.client.force_login(self.supervisor)

        response = self.client.get(
            reverse("workorders:create"),
            HTTP_ACCEPT_LANGUAGE="es",
        )

        self.assertContains(response, "Crear orden de trabajo")
        self.assertContains(response, "Seleccione primero un almacén")
        self.assertContains(response, "Configure la frecuencia")
