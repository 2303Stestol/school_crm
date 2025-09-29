from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from crm import models
from crm.forms import EnrollmentForm


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
        self.assertEqual(attendance.exercise_progress()["total"], 0)

    def test_exercise_progress_counts(self) -> None:
        lesson = models.Lesson.objects.create(course=self.course, date=date(2024, 4, 1))
        attendance = models.Attendance.objects.create(lesson=lesson, student=self.student)
        exercise_a = models.Exercise.objects.create(lesson=lesson, title="Упражнение 1")
        exercise_b = models.Exercise.objects.create(lesson=lesson, title="Упражнение 2")
        models.ExerciseResult.objects.create(
            exercise=exercise_a,
            student=self.student,
            status=models.ExerciseStatus.SOLVED,
        )
        models.ExerciseResult.objects.create(
            exercise=exercise_b,
            student=self.student,
            status=models.ExerciseStatus.PARTIAL,
        )
        progress = attendance.exercise_progress()
        self.assertEqual(progress["total"], 2)
        self.assertEqual(progress["solved"], 1)
        self.assertEqual(progress["partial"], 1)
        self.assertEqual(progress["pending"], 0)


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

    def test_student_can_be_enrolled_to_multiple_courses(self) -> None:
        first_enrollment = models.Enrollment.objects.create(
            student=self.student,
            course=self.course,
            start_date=date(2024, 1, 1),
        )
        second_course = models.Course.objects.create(
            title="Геометрия",
            description="Геометрические задачи",
            teacher=self.teacher_user,
        )
        second_enrollment = models.Enrollment.objects.create(
            student=self.student,
            course=second_course,
            start_date=date(2024, 2, 1),
        )
        self.assertTrue(first_enrollment.is_active)
        self.assertTrue(second_enrollment.is_active)
        self.assertEqual(self.student.enrollments.count(), 2)

    def test_enrollment_form_blocks_duplicate_active(self) -> None:
        models.Enrollment.objects.create(
            student=self.student,
            course=self.course,
            start_date=date(2024, 1, 1),
        )
        form = EnrollmentForm(
            data={
                "student": self.student.pk,
                "course": self.course.pk,
                "start_date": "2024-03-01",
                "end_date": "",
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
        self.assertIn("у этого ученика уже есть активная запись", form.errors["__all__"][0].lower())

