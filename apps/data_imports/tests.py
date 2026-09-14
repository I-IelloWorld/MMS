from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.assets.models import AssetCategory, Equipment
from apps.facilities.models import Warehouse

from .models import ImportBatch
from .services import process_equipment_import


class EquipmentImportTests(TestCase):
    def test_csv_import_creates_valid_row_and_reports_invalid_row(self):
        user = get_user_model().objects.create_user(username="admin", email="admin@example.com", password="test-pass")
        warehouse = Warehouse.objects.create(code="WH-01", name="测试仓")
        AssetCategory.objects.create(code="CONVEYOR", name="输送机")
        upload = SimpleUploadedFile(
            "equipment.csv",
            (
                "asset_code,name,category_code,criticality,status\n"
                "CV-001,主输送机,CONVEYOR,HIGH,ACTIVE\n"
                "CV-002,未知设备,UNKNOWN,MEDIUM,ACTIVE\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        batch = ImportBatch.objects.create(warehouse=warehouse, created_by=user, source_file=upload)

        process_equipment_import(batch)
        batch.refresh_from_db()

        self.assertEqual(batch.success_rows, 1)
        self.assertEqual(batch.failed_rows, 1)
        self.assertTrue(Equipment.objects.filter(warehouse=warehouse, asset_code="CV-001").exists())
        self.assertEqual(batch.errors.count(), 1)

    def test_import_rejects_row_for_a_different_target_warehouse(self):
        user = get_user_model().objects.create_user(
            username="import-user",
            email="import-user@example.com",
            password="1",
        )
        warehouse = Warehouse.objects.create(code="WH-A", name="目标仓")
        AssetCategory.objects.create(code="CONVEYOR", name="输送机")
        upload = SimpleUploadedFile(
            "equipment.csv",
            (
                "warehouse_code,asset_code,name,category_code\n"
                "WH-B,CV-009,错误仓设备,CONVEYOR\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        batch = ImportBatch.objects.create(
            warehouse=warehouse,
            created_by=user,
            source_file=upload,
        )

        process_equipment_import(batch)
        batch.refresh_from_db()

        self.assertEqual(batch.success_rows, 0)
        self.assertEqual(batch.failed_rows, 1)
        self.assertIn("与目标仓库 WH-A 不一致", batch.errors.get().error_message)

    def test_excel_template_contains_headers_and_dynamic_dropdowns(self):
        user = get_user_model().objects.create_superuser(
            username="template-admin",
            email="template-admin@example.com",
            password="1",
        )
        Warehouse.objects.create(code="WH-TEMPLATE", name="模板仓")
        AssetCategory.objects.create(code="ROBOT", name="机器人")
        self.client.force_login(user)

        response = self.client.get(reverse("data-imports:equipment-template"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("MMS_equipment_import_template.xlsx", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook["设备导入"]
        self.assertEqual(
            [cell.value for cell in sheet[1]],
            [
                "warehouse_code", "asset_code", "name", "category_code",
                "manufacturer", "model", "serial_number", "commissioned_on",
                "location_detail", "criticality", "status", "component_code",
                "component_name", "component_type",
            ],
        )
        self.assertEqual(workbook["选项"].sheet_state, "hidden")
        self.assertEqual(workbook["选项"]["A2"].value, "WH-TEMPLATE")
        self.assertEqual(workbook["选项"]["C2"].value, "ROBOT")
        validations = list(sheet.data_validations.dataValidation)
        self.assertSetEqual(
            {validation.formula1 for validation in validations},
            {"=WarehouseCodes", "=CategoryCodes", "=CriticalityCodes", "=EquipmentStatuses"},
        )

# Create your tests here.
