from django.db import migrations, models


def populate_timezones(apps, schema_editor):
    orders = apps.get_model("workorders", "WorkOrder").objects.using(schema_editor.connection.alias)
    warehouses = apps.get_model("facilities", "Warehouse").objects.using(schema_editor.connection.alias)
    valid_zones = {"America/New_York", "America/Chicago", "America/Los_Angeles"}
    for warehouse in warehouses.iterator():
        zone = warehouse.timezone if warehouse.timezone in valid_zones else "America/Chicago"
        orders.filter(warehouse_id=warehouse.pk).update(timezone=zone)


class Migration(migrations.Migration):
    dependencies = [
        ("workorders", "0007_workorder_recurrence_number"),
        ("facilities", "0003_alter_warehouse_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder", name="timezone",
            field=models.CharField(
                choices=[("America/Los_Angeles", "美西时间"), ("America/Chicago", "美中时间"), ("America/New_York", "美东时间")],
                default="America/Chicago", max_length=64, verbose_name="工单时区",
            ),
        ),
        migrations.RunPython(populate_timezones, migrations.RunPython.noop),
    ]
