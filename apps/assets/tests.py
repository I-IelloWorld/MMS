from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.facilities.models import Warehouse, WarehouseMembership, WarehouseRole

from .forms import EquipmentComponentAdminForm, EquipmentCreateForm
from .models import AssetCategory, Equipment, EquipmentComponent


class EquipmentStatusTests(TestCase):
    def test_equipment_has_required_operating_statuses(self):
        self.assertEqual(
            dict(Equipment.Status.choices),
            {
                "ACTIVE": "投产",
                "INACTIVE": "停用",
                "TRIAL": "试运行",
                "COMMISSIONING": "调试",
                "RETIRED": "废弃",
            },
        )


class EquipmentCreatePageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="equipment-editor",
            email="equipment-editor@example.com",
            password="1",
        )
        self.viewer = get_user_model().objects.create_user(
            username="equipment-viewer",
            email="equipment-viewer@example.com",
            password="1",
        )
        permission = Permission.objects.get(
            content_type__app_label="assets",
            codename="modify_equipment",
        )
        self.user.user_permissions.add(permission)
        role = WarehouseRole.objects.create(code="ASSET-EDITOR", name="设备录入员")
        self.warehouse = Warehouse.objects.create(code="CREATE-A", name="可录入仓")
        self.other_warehouse = Warehouse.objects.create(code="CREATE-B", name="其他仓")
        WarehouseMembership.objects.create(
            warehouse=self.warehouse,
            user=self.user,
            role=role,
        )
        self.category = AssetCategory.objects.create(code="CREATE-CAT", name="输送设备")

    def test_frontend_create_form_only_offers_authorized_warehouses(self):
        form = EquipmentCreateForm(user=self.user)

        self.assertQuerySetEqual(form.fields["warehouse"].queryset, [self.warehouse])
        self.assertQuerySetEqual(form.fields["category"].queryset, [self.category])

    def test_authorized_user_can_create_equipment_on_frontend(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("assets:equipment-create"),
            {
                "warehouse": self.warehouse.id,
                "category": self.category.id,
                "asset_code": "NEW-EQ-01",
                "name": "新设备",
                "manufacturer": "",
                "model": "",
                "serial_number": "",
                "commissioned_on": "",
                "location_detail": "A 区",
                "criticality": Equipment.Criticality.MEDIUM,
                "status": Equipment.Status.TRIAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        equipment = Equipment.objects.get(asset_code="NEW-EQ-01")
        self.assertEqual(equipment.warehouse, self.warehouse)
        self.assertEqual(equipment.status, Equipment.Status.TRIAL)

    def test_user_cannot_create_in_unauthorized_warehouse(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("assets:equipment-create"),
            {
                "warehouse": self.other_warehouse.id,
                "category": self.category.id,
                "asset_code": "FORGED-EQ",
                "name": "越权设备",
                "criticality": Equipment.Criticality.MEDIUM,
                "status": Equipment.Status.ACTIVE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("warehouse", response.context["form"].errors)
        self.assertFalse(Equipment.objects.filter(asset_code="FORGED-EQ").exists())

    def test_user_without_modify_permission_cannot_open_create_page(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("assets:equipment-create"))

        self.assertEqual(response.status_code, 403)


class EquipmentComponentAdminDependencyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.engineer = user_model.objects.create_user(
            username="asset-engineer",
            email="asset-engineer@example.com",
            password="test-pass",
        )
        self.other_engineer = user_model.objects.create_user(
            username="other-asset-engineer",
            email="other-asset-engineer@example.com",
            password="test-pass",
        )
        self.warehouse = Warehouse.objects.create(code="ASSET-A", name="设备一仓")
        self.other_warehouse = Warehouse.objects.create(code="ASSET-B", name="设备二仓")
        role = WarehouseRole.objects.create(
            code="ASSET-ENGINEER",
            name="设备工程师",
            can_receive_work_orders=True,
        )
        WarehouseMembership.objects.create(
            warehouse=self.warehouse,
            user=self.engineer,
            role=role,
        )
        WarehouseMembership.objects.create(
            warehouse=self.other_warehouse,
            user=self.other_engineer,
            role=role,
        )
        category = AssetCategory.objects.create(code="ASSET-CAT", name="输送设备")
        self.equipment = Equipment.objects.create(
            warehouse=self.warehouse,
            category=category,
            asset_code="ASSET-EQ-A",
            name="一号设备",
        )
        self.second_equipment = Equipment.objects.create(
            warehouse=self.warehouse,
            category=category,
            asset_code="ASSET-EQ-A2",
            name="二号设备",
        )
        self.other_equipment = Equipment.objects.create(
            warehouse=self.other_warehouse,
            category=category,
            asset_code="ASSET-EQ-B",
            name="其他仓设备",
        )
        self.parent = EquipmentComponent.objects.create(
            equipment=self.equipment,
            code="PARENT-A",
            name="一号总成",
        )
        self.sibling = EquipmentComponent.objects.create(
            equipment=self.equipment,
            code="SIBLING-A",
            name="一号子部件",
        )
        self.other_component = EquipmentComponent.objects.create(
            equipment=self.other_equipment,
            code="PARENT-B",
            name="其他仓总成",
        )

    def test_unbound_form_scopes_equipment_and_disables_parent(self):
        form = EquipmentComponentAdminForm(user=self.engineer)

        self.assertQuerySetEqual(
            form.fields["equipment"].queryset,
            [self.equipment, self.second_equipment],
            ordered=False,
        )
        self.assertFalse(form.fields["parent"].queryset.exists())
        self.assertIn("disabled", form.fields["parent"].widget.attrs)

    def test_bound_form_only_offers_components_from_selected_equipment(self):
        form = EquipmentComponentAdminForm(
            data={
                "equipment": self.equipment.id,
                "parent": self.parent.id,
                "code": "CHILD-A",
                "name": "下级部件",
                "component_type": "电气",
                "serial_number": "",
                "status": EquipmentComponent.Status.ACTIVE,
            },
            user=self.engineer,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertQuerySetEqual(
            form.fields["parent"].queryset,
            [self.parent, self.sibling],
            ordered=False,
        )
        self.assertNotIn("disabled", form.fields["parent"].widget.attrs)

    def test_cross_equipment_parent_is_rejected_by_form_and_model(self):
        form = EquipmentComponentAdminForm(
            data={
                "equipment": self.equipment.id,
                "parent": self.other_component.id,
                "code": "FORGED-A",
                "name": "伪造部件",
                "component_type": "",
                "serial_number": "",
                "status": EquipmentComponent.Status.ACTIVE,
            },
            user=self.engineer,
        )
        forged_component = EquipmentComponent(
            equipment=self.equipment,
            parent=self.other_component,
            code="FORGED-MODEL-A",
            name="模型伪造部件",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("parent", form.errors)
        with self.assertRaises(ValidationError):
            forged_component.full_clean()

    def test_edit_form_excludes_component_itself_from_parent_choices(self):
        child = EquipmentComponent.objects.create(
            equipment=self.equipment,
            parent=self.parent,
            code="CHILD-EDIT-A",
            name="待编辑部件",
        )

        form = EquipmentComponentAdminForm(instance=child, user=self.engineer)

        self.assertNotIn(child, form.fields["parent"].queryset)
        self.assertIn(self.parent, form.fields["parent"].queryset)
        self.assertEqual(
            form.fields["parent"].widget.attrs["data-current-component-id"],
            str(child.id),
        )

    def test_options_endpoint_returns_only_authorized_equipment_components(self):
        self.client.force_login(self.engineer)
        url = reverse("assets:component-options")

        response = self.client.get(
            url,
            {"equipment": self.equipment.id, "exclude": self.sibling.id},
        )
        inaccessible = self.client.get(url, {"equipment": self.other_equipment.id})
        invalid = self.client.get(url, {"equipment": "not-a-uuid"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["components"],
            [{"value": str(self.parent.id), "label": "PARENT-A · 一号总成"}],
        )
        self.assertEqual(inaccessible.json(), {"components": []})
        self.assertEqual(invalid.json(), {"components": []})

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_admin_add_page_loads_dependency_script(self):
        user_model = get_user_model()
        administrator = user_model.objects.create_superuser(
            username="asset-admin",
            email="asset-admin@example.com",
            password="test-pass",
        )
        self.client.force_login(administrator)

        response = self.client.get(reverse("admin:assets_equipmentcomponent_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/equipment-component-dependent-selects.js")
