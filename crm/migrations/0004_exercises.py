# Generated manually to introduce lesson exercises
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_create_default_groups"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="attendance",
            name="task_status",
        ),
        migrations.DeleteModel(
            name="TaskSubmission",
        ),
        migrations.DeleteModel(
            name="Task",
        ),
        migrations.CreateModel(
            name="Exercise",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                (
                    "lesson",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exercises",
                        to="crm.lesson",
                        verbose_name="Занятие",
                    ),
                ),
            ],
            options={
                "ordering": ("order", "created_at"),
                "verbose_name": "Упражнение",
                "verbose_name_plural": "Упражнения",
            },
        ),
        migrations.CreateModel(
            name="ExerciseResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Не решено"),
                            ("solved", "Решено"),
                            ("partial", "Частично"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="Статус",
                    ),
                ),
                ("comment", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="crm.exercise",
                        verbose_name="Упражнение",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exercise_results",
                        to="crm.student",
                        verbose_name="Ученик",
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
                "verbose_name": "Результат упражнения",
                "verbose_name_plural": "Результаты упражнений",
                "unique_together": {("exercise", "student")},
            },
        ),
    ]
