import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorders", "0005_workorder_task_duration_hours_alter_workorder_due_at"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="workorder", name="uniq_work_order_plan_occurrence",
        ),
        migrations.RemoveField(model_name="workorder", name="source_plan"),
        migrations.RemoveField(model_name="workorder", name="plan_due_at"),
        migrations.AlterField(
            model_name="workorder",
            name="recurrence_interval",
            field=models.PositiveIntegerField(
                default=1, validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="周期数值",
            ),
        ),
        migrations.AddConstraint(
            model_name="workorder",
            constraint=models.CheckConstraint(
                condition=~models.Q(schedule_type="RECURRING") | models.Q(recurrence_interval__gte=1),
                name="recurring_interval_positive",
            ),
        ),
    ]
