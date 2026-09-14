from datetime import datetime, timedelta, timezone as dt_timezone
from importlib import import_module
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.assets.models import AssetCategory, Equipment
from apps.facilities.models import Warehouse

from .forms import WorkOrderAdminChangeForm, WorkOrderAdminForm, WorkOrderCreateForm
from .models import WorkOrder
from .services import calculate_next_due, generate_recurring_work_orders


UTC = dt_timezone.utc
ZONES = ("America/New_York", "America/Chicago", "America/Los_Angeles")


class WorkOrderTimezoneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="tz-admin", email="tz-admin@example.com", timezone="America/Chicago",
        )
        cls.warehouse = Warehouse.objects.create(code="TZ", name="Timezone warehouse", timezone="America/New_York")
        cls.equipment = Equipment.objects.create(
            warehouse=cls.warehouse, asset_code="TZ", name="Timezone equipment",
            category=AssetCategory.objects.create(code="TZ", name="Timezone category"),
        )

    def data(self, zone="America/Chicago", start="2026-09-10T11:20"):
        return {
            "schedule_type": "RECURRING", "warehouse": self.warehouse.pk,
            "equipment": self.equipment.pk, "title": "Local inspection", "work_type": "INSPECTION",
            "priority": "MEDIUM", "timezone": zone, "due_at": start,
            "task_duration_hours": 24, "recurrence_unit": "DAY", "recurrence_interval": 1,
            "recurrence_end_at": "",
        }

    def source(self, zone="America/Chicago", start="2026-09-10T11:20", **changes):
        data = self.data(zone, start)
        data.update(changes)
        form = WorkOrderCreateForm(data=data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        order = form.save(commit=False)
        order.number = f"WO-TZ-{WorkOrder.objects.count()}"
        order.save()
        return order

    def test_all_three_zones_parse_independently_of_server_or_account_zone(self):
        for form_class in (WorkOrderCreateForm, WorkOrderAdminForm):
            for zone, utc_hour in zip(ZONES, (15, 16, 18)):
                with self.subTest(form=form_class.__name__, zone=zone), timezone.override("Asia/Shanghai"):
                    data = self.data(zone)
                    data["recurrence_end_at"] = "2026-09-12T11:20"
                    form = form_class(data=data, user=self.user)
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.cleaned_data["due_at"], datetime(2026, 9, 10, utc_hour, 20, tzinfo=UTC))
                    self.assertEqual(form.cleaned_data["recurrence_end_at"], datetime(2026, 9, 12, utc_hour, 20, tzinfo=UTC))
                    self.assertEqual(timezone.get_current_timezone_name(), "Asia/Shanghai")

    def test_invalid_and_missing_timezones_are_rejected(self):
        for value in ("", "UTC", "Asia/Shanghai", "Unknown/Zone"):
            form = WorkOrderCreateForm(data=self.data(value), user=self.user)
            self.assertFalse(form.is_valid())
            self.assertIn("timezone", form.errors)

    def test_new_form_defaults_to_account_timezone_and_only_offers_three_zones(self):
        self.user.timezone = "America/Los_Angeles"
        form = WorkOrderCreateForm(user=self.user)
        self.assertEqual(form["timezone"].value(), "America/Los_Angeles")
        self.assertEqual({value for value, label in form.fields["timezone"].choices}, set(ZONES))

    def test_one_time_public_creation_starts_at_selected_time_with_full_24_hours(self):
        self.client.force_login(self.user)
        data = self.data()
        data["schedule_type"] = "ONE_TIME"
        data["recurrence_unit"] = ""
        now = datetime(2026, 9, 10, 16, 20, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.post(reverse("workorders:create"), data)
            self.assertEqual(response.status_code, 302)
            order = WorkOrder.objects.get()
            self.assertEqual(order.due_at, now)
            self.assertEqual(order.remaining_hours, 24)
            self.assertEqual(order.timezone, "America/Chicago")
            self.assertIsNone(order.next_occurrence_at)
        with patch("django.utils.timezone.now", return_value=now - timedelta(minutes=1)):
            response = self.client.get(reverse("dashboard:home"))
            self.assertNotIn(order, response.context["recent_work_orders"])

    def test_recurring_generation_obeys_timezone_and_inherits_it(self):
        source = self.source()
        due = datetime(2026, 9, 11, 16, 20, tzinfo=UTC)
        self.assertEqual(source.next_occurrence_at, due)
        self.assertEqual(generate_recurring_work_orders(due - timedelta(seconds=1)), [])
        with patch("django.utils.timezone.now", return_value=due):
            orders = generate_recurring_work_orders(due)
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0].timezone, source.timezone)
            self.assertEqual(orders[0].remaining_hours, 24)
            self.assertEqual(orders[0].recurrence_number, 2)

    def test_edit_roundtrip_keeps_local_time_and_does_not_reset_schedule(self):
        source = self.source()
        generate_recurring_work_orders(source.next_occurrence_at)
        source.refresh_from_db()
        original_next = source.next_occurrence_at
        with timezone.override("America/Los_Angeles"):
            form = WorkOrderAdminChangeForm(instance=source, user=self.user)
            self.assertIn('value="2026-09-10T11:20"', str(form["due_at"]))
            data = self.data()
            data.update(status=source.status, recurrence_active=True)
            bound = WorkOrderAdminChangeForm(data=data, instance=source, user=self.user)
            self.assertTrue(bound.is_valid(), bound.errors)
            self.assertNotIn("due_at", bound.changed_data)
            updated = bound.save()
        self.assertEqual(updated.due_at, datetime(2026, 9, 10, 16, 20, tzinfo=UTC))
        self.assertEqual(updated.next_occurrence_at, original_next)

    def test_changing_timezone_reinterprets_entered_local_time(self):
        source = self.source()
        data = self.data("America/New_York")
        data.update(status=source.status, recurrence_active=True)
        form = WorkOrderAdminChangeForm(data=data, instance=source, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.due_at, datetime(2026, 9, 10, 15, 20, tzinfo=UTC))
        self.assertEqual(updated.next_occurrence_at, datetime(2026, 9, 11, 15, 20, tzinfo=UTC))

    def test_invalid_dst_input_is_reported_on_the_datetime_field(self):
        for zone in ZONES:
            for wall_time in ("2026-03-08T02:30", "2026-11-01T01:30"):
                with self.subTest(zone=zone, wall_time=wall_time):
                    form = WorkOrderCreateForm(data=self.data(zone, wall_time), user=self.user)
                    self.assertFalse(form.is_valid())
                    self.assertIn("due_at", form.errors)

    def test_admin_uses_selected_zone_for_create_edit_and_readonly_dates(self):
        self.client.force_login(self.user)
        data = self.data("America/Los_Angeles")
        data.update({"tasks-TOTAL_FORMS": "0", "tasks-INITIAL_FORMS": "0", "tasks-MIN_NUM_FORMS": "0", "tasks-MAX_NUM_FORMS": "1000"})
        response = self.client.post(reverse("admin:workorders_workorder_add"), data)
        self.assertEqual(response.status_code, 302)
        source = WorkOrder.objects.get()
        self.assertEqual(source.due_at, datetime(2026, 9, 10, 18, 20, tzinfo=UTC))
        edit = self.client.get(reverse("admin:workorders_workorder_change", args=[source.pk]))
        self.assertContains(edit, 'value="2026-09-10T11:20"')
        self.assertContains(edit, "2026-09-11 11:20")
        self.assertContains(edit, "America/Los_Angeles")
        response = self.client.get(reverse("admin:workorders_workorder_changelist"))
        self.assertContains(response, "2026-09-10 11:20")
        self.assertContains(response, "美西时间")

    def test_pages_and_report_display_order_timezone(self):
        source = self.source("America/Los_Angeles")
        self.client.force_login(self.user)
        for name, args in (("workorders:list", []), ("workorders:detail", [source.pk]), ("assets:equipment-detail", [source.equipment_id])):
            response = self.client.get(reverse(name, args=args))
            self.assertContains(response, "2026-09-10 11:20")
            self.assertContains(response, "美西时间")
        with patch("django.utils.timezone.now", return_value=source.due_at):
            response = self.client.get(reverse("dashboard:home"))
            self.assertContains(response, "09-10 11:20")
            response = self.client.get(reverse("dashboard:report", args=["daily"]))
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook["工单明细"]["I2"].value, datetime(2026, 9, 10, 11, 20))
        self.assertEqual(workbook["工单明细"]["T2"].value, "America/Los_Angeles")

    def test_timezone_migration_preserves_existing_absolute_times(self):
        source = self.source()
        before = (source.due_at, source.next_occurrence_at, source.recurrence_end_at)
        migration = import_module("apps.workorders.migrations.0008_workorder_timezone")
        migration.populate_timezones(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        source.refresh_from_db()
        self.assertEqual(source.timezone, self.warehouse.timezone)
        self.assertEqual((source.due_at, source.next_occurrence_at, source.recurrence_end_at), before)

    def test_dst_generation_preserves_local_hour_and_exact_task_duration(self):
        source = self.source("America/Chicago", "2026-03-07T09:00", recurrence_end_at="2026-03-09T09:00")
        orders = generate_recurring_work_orders(datetime(2026, 3, 10, tzinfo=UTC))
        self.assertEqual([o.due_at for o in orders], [datetime(2026, 3, 8, 14, tzinfo=UTC), datetime(2026, 3, 9, 14, tzinfo=UTC)])
        for order in orders:
            self.assertEqual(order.due_at.astimezone(ZoneInfo(order.timezone)).hour, 9)
            self.assertEqual(order.deadline_at - order.due_at, timedelta(hours=24))
        source.refresh_from_db()
        self.assertFalse(source.recurrence_active)


class CalendarTimezoneTests(SimpleTestCase):
    def next_due(self, current, zone, anchor=None, unit="DAY", interval=1):
        return calculate_next_due(current.astimezone(UTC), unit, interval, timezone_name=zone, anchor=(anchor or current).astimezone(UTC))

    def test_spring_and_fall_preserve_local_clock_in_all_supported_zones(self):
        for zone in ZONES:
            for month, day, expected_hours in ((3, 7, 23), (10, 31, 25)):
                with self.subTest(zone=zone, month=month):
                    start = datetime(2026, month, day, 9, tzinfo=ZoneInfo(zone))
                    following = self.next_due(start, zone)
                    self.assertEqual(following.astimezone(ZoneInfo(zone)).hour, 9)
                    self.assertEqual(following - start.astimezone(UTC), timedelta(hours=expected_hours))

    def test_nonexistent_recurring_time_advances_once_then_restores_original_clock(self):
        zone = "America/Chicago"
        start = datetime(2026, 3, 7, 2, 30, tzinfo=ZoneInfo(zone))
        following = self.next_due(start, zone)
        self.assertEqual(following.astimezone(ZoneInfo(zone)).strftime("%m-%d %H:%M"), "03-08 03:30")
        third = self.next_due(following, zone, anchor=start)
        self.assertEqual(third.astimezone(ZoneInfo(zone)).strftime("%m-%d %H:%M"), "03-09 02:30")

    def test_fall_back_ambiguous_recurring_time_uses_first_occurrence(self):
        zone = "America/New_York"
        start = datetime(2026, 10, 31, 1, 30, tzinfo=ZoneInfo(zone))
        following = self.next_due(start, zone)
        self.assertEqual(following, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
        self.assertEqual(self.next_due(following, zone, anchor=start), datetime(2026, 11, 2, 6, 30, tzinfo=UTC))

    def test_week_month_quarter_and_year_use_local_calendar(self):
        zone = "America/Chicago"
        start = datetime(2026, 2, 28, 9, tzinfo=ZoneInfo(zone))
        for unit, expected in (("WEEK", "2026-03-07 09:00"), ("MONTH", "2026-03-28 09:00"), ("QUARTER", "2026-05-28 09:00"), ("YEAR", "2027-02-28 09:00")):
            with self.subTest(unit=unit):
                self.assertEqual(self.next_due(start, zone, unit=unit).astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M"), expected)

    def test_month_end_anchor_is_preserved_after_short_month(self):
        zone = "America/Chicago"
        start = datetime(2026, 1, 31, 9, tzinfo=ZoneInfo(zone))
        february = self.next_due(start, zone, unit="MONTH")
        march = self.next_due(february, zone, anchor=start, unit="MONTH")
        self.assertEqual(february.astimezone(ZoneInfo(zone)).day, 28)
        self.assertEqual(march.astimezone(ZoneInfo(zone)).strftime("%m-%d %H:%M"), "03-31 09:00")

    def test_task_duration_is_elapsed_hours_even_before_database_roundtrip(self):
        due = datetime(2026, 3, 7, 9, tzinfo=ZoneInfo("America/Chicago"))
        order = WorkOrder(due_at=due, task_duration_hours=24)
        self.assertEqual(order.deadline_at, datetime(2026, 3, 8, 15, tzinfo=UTC))
