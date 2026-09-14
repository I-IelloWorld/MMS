import django.core.validators
from django.db import migrations, models


def number_existing_occurrences(apps, schema_editor):
    orders = apps.get_model("workorders", "WorkOrder").objects.using(schema_editor.connection.alias)
    source_ids = set(orders.filter(schedule_type="RECURRING").values_list("pk", flat=True))
    source_ids.update(orders.filter(recurrence_source__isnull=False).values_list("recurrence_source_id", flat=True))
    for source_id in source_ids:
        children = list(orders.filter(recurrence_source_id=source_id).order_by("due_at", "created_at", "pk"))
        for number, child in enumerate(children, start=2):
            child.recurrence_number = number
        if children:
            orders.bulk_update(children, ["recurrence_number"])
        orders.filter(pk=source_id).update(recurrence_number=1, last_recurrence_number=len(children) + 1)


class Migration(migrations.Migration):
    dependencies = [
        ("workorders", "0006_remove_legacy_plan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder", name="recurrence_number",
            field=models.PositiveIntegerField(
                null=True, blank=True, editable=False,
                validators=[django.core.validators.MinValueValidator(1)], verbose_name="周期期次",
            ),
        ),
        migrations.AddField(
            model_name="workorder", name="last_recurrence_number",
            field=models.PositiveIntegerField(
                default=1, editable=False,
                validators=[django.core.validators.MinValueValidator(1)], verbose_name="最近生成期次",
            ),
        ),
        migrations.RunPython(number_existing_occurrences, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="workorder",
            constraint=models.UniqueConstraint(
                fields=("recurrence_source", "recurrence_number"),
                condition=models.Q(recurrence_source__isnull=False, recurrence_number__isnull=False),
                name="uniq_recurring_work_order_number",
            ),
        ),
    ]
