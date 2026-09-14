from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.assets.models import AssetCategory, Equipment, EquipmentComponent
from apps.facilities.models import Warehouse
from apps.workorders.models import WorkOrder
from apps.workorders.services import calculate_next_due, work_order_number


class Command(BaseCommand):
    help = "创建用于本地演示的仓库、自动化设备、部件和周期性工单。"

    def handle(self, *args, **options):
        conveyor, _ = AssetCategory.objects.get_or_create(code="CONVEYOR", defaults={"name": "输送系统"})
        robot, _ = AssetCategory.objects.get_or_create(code="ROBOT", defaults={"name": "工业机器人"})
        asrs, _ = AssetCategory.objects.get_or_create(code="ASRS", defaults={"name": "自动存取系统"})

        warehouses = []
        for code, name, city in (
            ("CPF", "洛杉矶1号仓库", "Fontana, CA"),
            ("HNB", "休斯顿仓库", "Houston, TX"),
            ("SPR", "芝加哥仓库", "Chicago, IL"),
        ):
            warehouse, _ = Warehouse.objects.get_or_create(
                code=code,
                defaults={"name": name, "address": city, "timezone": "America/Chicago"},
            )
            warehouses.append(warehouse)

        equipment_specs = (
            (warehouses[0], conveyor, "CV-001", "入库主输送线", "A 区 1 层", "CRITICAL"),
            (warehouses[0], robot, "RB-014", "码垛机器人 14", "出库工作站 4", "HIGH"),
            (warehouses[0], asrs, "ASRS-01", "高位库堆垛机", "高位库巷道 1", "CRITICAL"),
            (warehouses[1], conveyor, "CV-204", "分拣环线 2", "分拣区", "HIGH"),
            (warehouses[1], robot, "RB-022", "拆码垛机器人 22", "入库工作站 2", "MEDIUM"),
            (warehouses[2], asrs, "ASRS-07", "料箱穿梭车系统", "小件库", "HIGH"),
        )
        equipment_items = []
        for warehouse, category, code, name, location, criticality in equipment_specs:
            equipment, _ = Equipment.objects.update_or_create(
                warehouse=warehouse,
                asset_code=code,
                defaults={
                    "category": category,
                    "name": name,
                    "manufacturer": "MMS Demo Automation",
                    "model": "AX-2026",
                    "commissioned_on": date(2024, 6, 1),
                    "location_detail": location,
                    "criticality": criticality,
                },
            )
            equipment_items.append(equipment)
            EquipmentComponent.objects.get_or_create(
                equipment=equipment,
                code="DRIVE-01",
                defaults={"name": "主驱动单元", "component_type": "DRIVE"},
            )

        for offset, equipment in enumerate(equipment_items):
            due_at = timezone.now() + timedelta(days=offset + 1)
            WorkOrder.objects.get_or_create(
                warehouse=equipment.warehouse,
                equipment=equipment,
                title=f"{equipment.name} · 月度预防性维保",
                schedule_type=WorkOrder.ScheduleType.RECURRING,
                defaults={
                    "number": work_order_number(),
                    "component": equipment.components.first(),
                    "description": "完成清洁、紧固、润滑和安全检查。",
                    "work_type": WorkOrder.Type.PREVENTIVE,
                    "timezone": equipment.warehouse.timezone,
                    "due_at": due_at,
                    "recurrence_unit": WorkOrder.CycleUnit.MONTH,
                    "recurrence_interval": 1,
                    "next_occurrence_at": calculate_next_due(
                        due_at, WorkOrder.CycleUnit.MONTH, 1,
                        timezone_name=equipment.warehouse.timezone, anchor=due_at,
                    ),
                    "recurrence_active": True,
                    "priority": WorkOrder.Priority.HIGH if equipment.criticality in {"HIGH", "CRITICAL"} else WorkOrder.Priority.MEDIUM,
                },
            )
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
