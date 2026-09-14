from django.db import migrations


def enable_staff_for_existing_group_members(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(groups__isnull=False, is_staff=False).distinct().update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.RunPython(enable_staff_for_existing_group_members, migrations.RunPython.noop),
    ]
