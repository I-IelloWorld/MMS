from django.contrib.auth import get_user_model
from django.test import TestCase

from .access import accessible_warehouses
from .models import Warehouse, WarehouseMembership, WarehouseRole


class WarehouseAccessTests(TestCase):
    def test_user_only_receives_authorized_warehouses(self):
        user = get_user_model().objects.create_user(username="engineer", email="engineer@example.com", password="test-pass")
        allowed = Warehouse.objects.create(code="A", name="授权仓")
        Warehouse.objects.create(code="B", name="其他仓")
        role = WarehouseRole.objects.get(code="ENGINEER")
        WarehouseMembership.objects.create(warehouse=allowed, user=user, role=role)

        self.assertQuerySetEqual(accessible_warehouses(user), [allowed])

    def test_warehouse_timezone_has_only_three_us_choices(self):
        field = Warehouse._meta.get_field("timezone")

        self.assertEqual(
            [value for value, _label in field.choices],
            ["America/Los_Angeles", "America/Chicago", "America/New_York"],
        )

# Create your tests here.
