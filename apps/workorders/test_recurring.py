from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.apps import apps
from django.core.management import get_commands
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.assets.models import AssetCategory, Equipment
from apps.facilities.models import Warehouse, WarehouseMembership, WarehouseRole
from apps.notifications.models import Notification, NotificationRecipient

from .forms import WorkOrderAdminChangeForm
from .models import WorkOrder, WorkOrderTask
from .scheduler import run_scheduler
from .services import calculate_next_due, generate_recurring_work_orders


class RecurringCatchupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.start = datetime(2026, 9, 1, 9, tzinfo=dt_timezone.utc)
        cls.warehouse = Warehouse.objects.create(code="CATCHUP", name="Catch-up warehouse")
        cls.user = get_user_model().objects.create_user(username="scheduler-user", email="scheduler@example.com")
        cls.role = WarehouseRole.objects.create(code="SCHEDULER", name="Engineer", can_receive_work_orders=True)
        WarehouseMembership.objects.create(warehouse=cls.warehouse, user=cls.user, role=cls.role)
        cls.equipment = Equipment.objects.create(
            warehouse=cls.warehouse, asset_code="CATCHUP-EQ", name="Equipment",
            category=AssetCategory.objects.create(code="CATCHUP-CAT", name="Category"),
        )

    def source(self, **changes):
        fields = dict(
            number="WO-CATCHUP", title="Daily inspection", warehouse=self.warehouse,
            equipment=self.equipment, due_at=self.start, task_duration_hours=8,
            schedule_type=WorkOrder.ScheduleType.RECURRING,
            recurrence_unit=WorkOrder.CycleUnit.DAY, recurrence_interval=1,
            recurrence_active=True, next_occurrence_at=self.start + timedelta(days=1),
            recurrence_end_at=self.start + timedelta(days=4), assignee=self.user,
        )
        fields.update(changes)
        return WorkOrder.objects.create(**fields)

    def test_all_missed_occurrences_are_generated_once_through_end_time(self):
        source = self.source(status=WorkOrder.Status.CLOSED)
        WorkOrderTask.objects.create(
            work_order=source, sequence=1, title="Photo inspection", requires_photo=True,
            status=WorkOrderTask.Status.DONE, result="Old result", completed_by=self.user,
            completed_at=self.start,
        )
        now = self.start + timedelta(days=10)

        orders = generate_recurring_work_orders(now)

        self.assertEqual([o.due_at for o in orders], [self.start + timedelta(days=i) for i in range(1, 5)])
        self.assertEqual([o.recurrence_number for o in orders], [2, 3, 4, 5])
        for order in orders:
            self.assertEqual(order.status, WorkOrder.Status.ASSIGNED)
            self.assertEqual(order.assignee, self.user)
            self.assertEqual(order.deadline_at, order.due_at + timedelta(hours=8))
            task = order.tasks.get()
            self.assertTrue(task.requires_photo)
            self.assertEqual(task.status, WorkOrderTask.Status.PENDING)
            self.assertEqual(task.result, "")
            self.assertFalse(task.photo)
            self.assertIsNone(task.completed_by)
            self.assertEqual(NotificationRecipient.objects.filter(notification__entity_id=order.pk, user=self.user).count(), 1)
        source.refresh_from_db()
        self.assertFalse(source.recurrence_active)
        self.assertIsNone(source.next_occurrence_at)
        self.assertEqual(source.status, WorkOrder.Status.CLOSED)
        self.assertEqual(source.recurrence_number, 1)
        self.assertEqual(source.last_recurrence_number, 5)
        self.assertEqual(generate_recurring_work_orders(now), [])
        self.assertEqual(Notification.objects.count(), 4)

    def test_scan_limit_defers_remaining_catchup_until_next_invocation(self):
        source = self.source()
        now = self.start + timedelta(days=10)

        first_batch = generate_recurring_work_orders(now, max_occurrences=2)

        self.assertEqual(len(first_batch), 2)
        source.refresh_from_db()
        self.assertTrue(source.recurrence_active)
        self.assertEqual(source.next_occurrence_at, self.start + timedelta(days=3))

        second_batch = generate_recurring_work_orders(now, max_occurrences=2)

        self.assertEqual(len(second_batch), 2)
        source.refresh_from_db()
        self.assertFalse(source.recurrence_active)
        self.assertIsNone(source.next_occurrence_at)

    def test_deleting_latest_occurrence_does_not_reuse_cycle_number(self):
        source = self.source()
        first = generate_recurring_work_orders(self.start + timedelta(days=1))[0]
        self.assertEqual(first.recurrence_number, 2)
        first.delete()
        second = generate_recurring_work_orders(self.start + timedelta(days=2))[0]
        self.assertEqual(second.recurrence_number, 3)
        self.assertEqual(generate_recurring_work_orders(self.start + timedelta(days=2)), [])
        source.refresh_from_db()
        self.assertEqual(source.last_recurrence_number, 3)

    def test_cycle_titles_follow_language_without_modifying_original_title(self):
        source = self.source(title="Inspection " + "x" * 169)
        order = generate_recurring_work_orders(self.start + timedelta(days=1))[0]
        for language, label in (("zh-hans", "（第 2 期）"), ("en", "(Cycle 2)"), ("es", "(Ciclo 2)")):
            with self.subTest(language=language), override(language):
                self.assertEqual(order.display_title, f"{source.title} {label}")
        order.refresh_from_db()
        self.assertEqual(order.title, source.title)
        self.assertLessEqual(len(order.title), 180)
        self.client.force_login(self.user)
        response = self.client.get(reverse("workorders:list"))
        self.assertContains(response, "（第 2 期）")
        detail = self.client.get(reverse("workorders:detail", args=[order.pk]))
        self.assertContains(detail, order.display_title)

    def test_one_time_order_has_no_cycle_label(self):
        order = self.source(schedule_type=WorkOrder.ScheduleType.ONE_TIME)
        self.assertEqual(order.display_title, order.title)
        self.assertEqual(order.recurrence_label, "")

    def test_existing_orders_backfill_in_scheduled_order_without_changing_times(self):
        source = self.source()
        late = WorkOrder.objects.create(
            number="WO-LATE", title=source.title, warehouse=self.warehouse,
            equipment=self.equipment, recurrence_source=source, due_at=self.start + timedelta(days=2),
        )
        early = WorkOrder.objects.create(
            number="WO-EARLY", title=source.title, warehouse=self.warehouse,
            equipment=self.equipment, recurrence_source=source, due_at=self.start + timedelta(days=1),
        )
        once = self.source(number="WO-NONRECURRING", schedule_type=WorkOrder.ScheduleType.ONE_TIME)
        before = list(WorkOrder.objects.order_by("pk").values("pk", "title", "due_at", "created_at", "next_occurrence_at"))
        migration = import_module("apps.workorders.migrations.0007_workorder_recurrence_number")
        migration.number_existing_occurrences(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        for order in (source, early, late, once):
            order.refresh_from_db()
        self.assertEqual([o.recurrence_number for o in (source, early, late, once)], [1, 2, 3, None])
        self.assertEqual(source.last_recurrence_number, 3)
        self.assertEqual(before, list(WorkOrder.objects.order_by("pk").values("pk", "title", "due_at", "created_at", "next_occurrence_at")))

    def test_scan_never_generates_future_period_and_waits_until_exact_start(self):
        source = self.source(recurrence_end_at=None)
        self.assertEqual(generate_recurring_work_orders(self.start + timedelta(days=1, microseconds=-1)), [])
        orders = generate_recurring_work_orders(self.start + timedelta(days=2))
        self.assertEqual(len(orders), 2)
        source.refresh_from_db()
        self.assertEqual(source.next_occurrence_at, self.start + timedelta(days=3))
        self.assertTrue(source.recurrence_active)
        self.assertEqual(generate_recurring_work_orders(self.start + timedelta(days=2)), [])

    def test_existing_occurrence_does_not_block_later_periods(self):
        source = self.source()
        existing = WorkOrder.objects.create(
            number="WO-EXISTING", title=source.title, warehouse=self.warehouse,
            equipment=self.equipment, recurrence_source=source, due_at=source.next_occurrence_at,
        )
        orders = generate_recurring_work_orders(self.start + timedelta(days=3))
        self.assertEqual(len(orders), 2)
        self.assertEqual(source.generated_occurrences.count(), 3)
        self.assertNotIn(existing.pk, [o.pk for o in orders])

    def test_invalid_schedule_does_not_block_other_sources(self):
        self.source(number="WO-INVALID", recurrence_unit="INVALID")
        source = self.source()
        with self.assertLogs("apps.workorders.services", level="ERROR"):
            orders = generate_recurring_work_orders(self.start + timedelta(days=2))
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(order.recurrence_source_id == source.pk for order in orders))

    def test_paused_cancelled_one_time_and_finished_schedules_do_not_generate(self):
        source = self.source(recurrence_active=False)
        self.source(number="WO-CANCELLED", status=WorkOrder.Status.CANCELLED)
        self.source(number="WO-ONCE", schedule_type=WorkOrder.ScheduleType.ONE_TIME)
        ended = self.source(number="WO-ENDED", recurrence_end_at=self.start + timedelta(hours=1))
        self.assertEqual(generate_recurring_work_orders(self.start + timedelta(days=10)), [])
        ended.refresh_from_db()
        self.assertFalse(ended.recurrence_active)
        source.refresh_from_db()
        self.assertFalse(source.recurrence_active)

    def test_monthly_catchup_respects_interval_and_end(self):
        source = self.source(recurrence_unit=WorkOrder.CycleUnit.MONTH, recurrence_interval=2,
                             next_occurrence_at=datetime(2026, 11, 1, 10, tzinfo=dt_timezone.utc),
                             recurrence_end_at=datetime(2027, 1, 1, 10, tzinfo=dt_timezone.utc))
        orders = generate_recurring_work_orders(datetime(2027, 2, 1, tzinfo=dt_timezone.utc))
        self.assertEqual([o.due_at.month for o in orders], [11, 1])
        self.assertEqual(source.generated_occurrences.count(), 2)

    def test_completed_first_order_does_not_fill_dashboard_queue(self):
        source = self.source(status=WorkOrder.Status.CLOSED)
        orders = generate_recurring_work_orders(self.start + timedelta(days=3))
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual({o.pk for o in response.context["recent_work_orders"]}, {o.pk for o in orders})
        self.assertNotIn(source.pk, {o.pk for o in response.context["recent_work_orders"]})

    def test_extending_finished_schedule_resumes_after_last_generated_occurrence(self):
        source = self.source()
        generate_recurring_work_orders(self.start + timedelta(days=10))
        source.refresh_from_db()
        data = {
            "schedule_type": source.schedule_type, "warehouse": self.warehouse.pk,
            "equipment": self.equipment.pk, "title": source.title, "work_type": source.work_type,
            "priority": source.priority, "status": source.status, "due_at": source.due_at,
            "timezone": source.timezone,
            "task_duration_hours": 8, "recurrence_unit": "DAY", "recurrence_interval": 1,
            "recurrence_end_at": self.start + timedelta(days=6), "recurrence_active": True,
        }
        admin_user = get_user_model().objects.create_superuser(username="schedule-admin", email="schedule-admin@example.com")
        form = WorkOrderAdminChangeForm(data=data, instance=source, user=admin_user)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.next_occurrence_at, self.start + timedelta(days=5))
        self.assertEqual(len(generate_recurring_work_orders(self.start + timedelta(days=10))), 2)


class SchedulerRuntimeTests(SimpleTestCase):
    def test_invalid_intervals_are_rejected(self):
        for value in (0, -1):
            with self.assertRaises(ValueError):
                calculate_next_due(datetime.now(dt_timezone.utc), "DAY", value)

    @override_settings(MMS_SCHEDULER_INTERVAL_SECONDS=30)
    @patch("apps.workorders.scheduler.connections.close_all")
    @patch("apps.workorders.scheduler.close_old_connections")
    @patch("apps.workorders.scheduler.generate_recurring_work_orders")
    def test_scheduler_scans_immediately_and_retries_after_database_failure(self, generate, close_old, close_all):
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, True]
        generate.side_effect = [OperationalError("temporary lock"), []]
        with self.assertLogs("apps.workorders.scheduler", level="ERROR"):
            run_scheduler(stop)
        self.assertEqual(generate.call_count, 2)
        stop.wait.assert_called_with(30)
        close_all.assert_called_once()

    @override_settings(MMS_LOCAL_SCHEDULER=True)
    def test_runserver_starts_scheduler_only_after_binding_and_stops_it(self):
        from apps.common.management.commands.runserver import Command, StaticRunserver

        self.assertEqual(get_commands()["runserver"], "apps.common")
        command = Command(stdout=StringIO())

        def serving_process(*args, **kwargs):
            command.on_bind(8000)
            command.on_bind(8000)
            self.assertFalse(command.scheduler_stop.is_set())

        with patch.object(StaticRunserver, "inner_run", side_effect=serving_process), \
             patch.object(StaticRunserver, "on_bind"), \
             patch("apps.common.management.commands.runserver.Thread") as thread:
            command.inner_run()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        thread.return_value.join.assert_called_once()
        self.assertTrue(command.scheduler_stop.is_set())
