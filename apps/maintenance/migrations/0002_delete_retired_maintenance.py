from django.db import migrations


def delete_retired_permissions(apps, schema_editor):
    # Cascades also remove obsolete grants from users, groups and warehouse roles.
    content_types = apps.get_model("contenttypes", "ContentType")
    content_types.objects.using(schema_editor.connection.alias).filter(
        app_label="maintenance",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0001_initial"),
        ("workorders", "0006_remove_legacy_plan_fields"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("facilities", "0003_alter_warehouse_timezone"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("accounts", "0003_alter_user_timezone"),
    ]

    operations = [
        migrations.DeleteModel(name="MaintenancePlan"),
        migrations.DeleteModel(name="MaintenanceTemplateTask"),
        migrations.DeleteModel(name="MaintenanceTemplate"),
        migrations.RunPython(delete_retired_permissions, migrations.RunPython.noop),
    ]
