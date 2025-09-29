from django.conf import settings
from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    """Abstract base model that stores creation and update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Student(TimestampedModel):
    first_name = models.CharField("Имя", max_length=150)
    last_name = models.CharField("Фамилия", max_length=150)
    middle_name = models.CharField("Отчество", max_length=150, blank=True)
    birth_date = models.DateField("Дата рождения", blank=True, null=True)
    guardian_name = models.CharField("Имя родителя/опекуна", max_length=255, blank=True)
    guardian_phone = models.CharField("Телефон для связи", max_length=32, blank=True)
    guardians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="students",
        verbose_name="Аккаунты родителей",
        blank=True,
    )
    notes = models.TextField("Заметки", blank=True)

    class Meta:
        ordering = ("last_name", "first_name")
        verbose_name = "Ученик"
        verbose_name_plural = "Ученики"

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part).strip()


class Course(TimestampedModel):
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    schedule = models.CharField("Расписание", max_length=255, blank=True)
    capacity = models.PositiveIntegerField("Максимальное количество учеников", blank=True, null=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="courses",
        verbose_name="Преподаватель",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("title",)
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self) -> str:
        return self.title


class Enrollment(TimestampedModel):
    student = models.ForeignKey(
        Student, related_name="enrollments", on_delete=models.CASCADE, verbose_name="Ученик"
    )
    course = models.ForeignKey(
        Course, related_name="enrollments", on_delete=models.CASCADE, verbose_name="Курс"
    )
    start_date = models.DateField("Дата начала", default=timezone.now)
    end_date = models.DateField("Дата окончания", blank=True, null=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "Запись на курс"
        verbose_name_plural = "Записи на курсы"
        constraints = [
            models.UniqueConstraint(
                fields=("student", "course"),
                name="unique_active_enrollment",
                condition=models.Q(is_active=True),
            )
        ]

    def __str__(self) -> str:
        return f"{self.student.full_name} → {self.course.title}"


class Lesson(TimestampedModel):
    course = models.ForeignKey(
        Course, related_name="lessons", on_delete=models.CASCADE, verbose_name="Курс"
    )
    date = models.DateField("Дата занятия")
    topic = models.CharField("Тема", max_length=255, blank=True)

    class Meta:
        ordering = ("-date", "course__title")
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        unique_together = ("course", "date")

    def __str__(self) -> str:
        return f"{self.course.title} — {self.date:%d.%m.%Y}"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Присутствовал"
    ABSENT = "absent", "Отсутствовал"
    EXCUSED = "excused", "Уважительная причина"



class Attendance(TimestampedModel):
    lesson = models.ForeignKey(
        Lesson, related_name="attendances", on_delete=models.CASCADE, verbose_name="Занятие"
    )
    student = models.ForeignKey(
        Student, related_name="attendances", on_delete=models.CASCADE, verbose_name="Ученик"
    )
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )

    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ("-lesson__date", "student__last_name")
        verbose_name = "Посещаемость"
        verbose_name_plural = "Посещаемость"
        unique_together = ("lesson", "student")

    def __str__(self) -> str:
        return f"{self.lesson} — {self.student.full_name}: {self.get_status_display()}"


    def set_prefetched_results(self, results: list["ExerciseResult"]) -> None:
        self._prefetched_results = results

    def exercise_results(self):
        if hasattr(self, "_prefetched_results"):
            return self._prefetched_results
        return ExerciseResult.objects.filter(
            exercise__lesson=self.lesson, student=self.student
        ).select_related("exercise")

    def exercise_progress(self) -> dict[str, int]:
        results = list(self.exercise_results())
        total = len(results)
        solved = sum(1 for result in results if result.status == ExerciseStatus.SOLVED)
        partial = sum(1 for result in results if result.status == ExerciseStatus.PARTIAL)
        pending = total - solved - partial
        return {
            "total": total,
            "solved": solved,
            "partial": partial,
            "pending": pending,
        }


class ExerciseStatus(models.TextChoices):
    PENDING = "pending", "Не решено"
    SOLVED = "solved", "Решено"
    PARTIAL = "partial", "Частично"


class Exercise(TimestampedModel):
    lesson = models.ForeignKey(
        Lesson, related_name="exercises", on_delete=models.CASCADE, verbose_name="Занятие"
    )
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ("order", "created_at")
        verbose_name = "Упражнение"
        verbose_name_plural = "Упражнения"

    def __str__(self) -> str:
        return f"{self.lesson} — {self.title}"


class ExerciseResult(TimestampedModel):
    exercise = models.ForeignKey(
        Exercise, related_name="results", on_delete=models.CASCADE, verbose_name="Упражнение"
    )
    student = models.ForeignKey(
        Student,
        related_name="exercise_results",
        on_delete=models.CASCADE,
        verbose_name="Ученик",
    )
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=ExerciseStatus.choices,
        default=ExerciseStatus.PENDING,
    )
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "Результат упражнения"
        verbose_name_plural = "Результаты упражнений"
        unique_together = ("exercise", "student")

    def __str__(self) -> str:
        return f"{self.student.full_name} — {self.exercise.title}"


class Subscription(TimestampedModel):
    student = models.ForeignKey(
        Student, related_name="subscriptions", on_delete=models.CASCADE, verbose_name="Ученик"
    )
    course = models.ForeignKey(
        Course, related_name="subscriptions", on_delete=models.CASCADE, verbose_name="Курс"
    )
    lessons_included = models.PositiveIntegerField("Количество занятий", default=4)
    price = models.DecimalField("Стоимость", max_digits=9, decimal_places=2)
    start_date = models.DateField("Дата начала", default=timezone.now)
    end_date = models.DateField("Дата окончания", blank=True, null=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "Абонемент"
        verbose_name_plural = "Абонементы"

    def __str__(self) -> str:
        return f"{self.course.title} для {self.student.full_name}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Наличные"
    CARD = "card", "Карта"
    TRANSFER = "transfer", "Перевод"


class Payment(TimestampedModel):
    student = models.ForeignKey(
        Student, related_name="payments", on_delete=models.CASCADE, verbose_name="Ученик"
    )
    subscription = models.ForeignKey(
        Subscription,
        related_name="payments",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Абонемент",
    )
    amount = models.DecimalField("Сумма", max_digits=9, decimal_places=2)
    paid_at = models.DateTimeField("Дата оплаты", default=timezone.now)
    method = models.CharField(
        "Способ оплаты",
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ("-paid_at",)
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"

    def __str__(self) -> str:
        return f"{self.amount} ₽ — {self.student.full_name}"

