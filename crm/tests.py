from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from crm import models


class ModelTests(TestCase):
    def setUp(self) -> None:
        self.parent_group, _ = Group.objects.get_or_create(name="Родители")
        self.teacher_group, _ = Group.objects.get_or_create(name="Учителя")
        self.parent_user = get_user_model().objects.create_user("parent", "parent@example.com", "pass1234")
        self.teacher_user = get_user_model().objects.create_user("teacher", "teacher@example.com", "pass1234")
        self.parent_user.groups.add(self.parent_group)
        self.teacher_user.groups.add(self.teacher_group)
        self.student = models.Student.objects.create(
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            birth_date=date(2012, 5, 1),
            guardian_name="Мария Иванова",
            guardian_phone="+7 999 000-00-00",
        )
        self.student.guardians.add(self.parent_user)
        self.course = models.Course.objects.create(
            title="Подготовка к олимпиадам",
            description="Решение сложных задач",
            teacher=self.teacher_user,
        )

    def test_student_full_name(self) -> None:
        self.assertEqual(self.student.full_name, "Иванов Иван Иванович")

    def test_attendance_str(self) -> None:
        lesson = models.Lesson.objects.create(course=self.course, date=date(2024, 3, 10))
        attendance = models.Attendance.objects.create(lesson=lesson, student=self.student)
        self.assertIn("Иванов Иван Иванович", str(attendance))
        self.assertEqual(attendance.task_status, models.LessonTaskStatus.PENDING)

    def test_payment_creation(self) -> None:
        subscription = models.Subscription.objects.create(
            student=self.student,
            course=self.course,
            lessons_included=8,
            price=5000,
        )
        payment = models.Payment.objects.create(
            student=self.student,
            subscription=subscription,
            amount=2500,
            paid_at=timezone.now(),
        )
        self.assertEqual(payment.subscription, subscription)
        self.assertEqual(payment.student, self.student)
        self.assertEqual(str(payment), "2500 ₽ — Иванов Иван Иванович")

    def test_student_guardian_link(self) -> None:
        self.assertIn(self.parent_user, self.student.guardians.all())

