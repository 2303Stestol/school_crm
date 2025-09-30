from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from crm import models
from crm.forms import EnrollmentForm, GuardianLinkForm


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


    def test_lessons_balance_counts_debt(self) -> None:
        models.Subscription.objects.create(
            student=self.student,
            course=self.course,
            lessons_included=3,
            price=4500,
            purchase_date=date(2024, 1, 1),
        )
        statuses = [
            models.AttendanceStatus.PRESENT,
            models.AttendanceStatus.ABSENT,
            models.AttendanceStatus.PRESENT,
            models.AttendanceStatus.ABSENT,
            models.AttendanceStatus.EXCUSED,
        ]
        for index, status in enumerate(statuses, start=1):
            lesson = models.Lesson.objects.create(
                course=self.course,
                date=date(2024, 2, index),
            )
            models.Attendance.objects.create(
                lesson=lesson,
                student=self.student,
                status=status,
            )
        balance = self.student.lessons_balance()
        self.assertEqual(balance["purchased"], 3)
        self.assertEqual(balance["billable"], 4)
        self.assertEqual(balance["used"], 3)
        self.assertEqual(balance["remaining"], 0)
        self.assertEqual(balance["debt"], 1)

    def test_student_guardian_link(self) -> None:
        self.assertIn(self.parent_user, self.student.guardians.all())

    def test_guardian_link_form_adds_parent(self) -> None:
        new_parent = get_user_model().objects.create_user(
            "another_parent", "another@example.com", "pass1234"
        )
        new_parent.groups.add(self.parent_group)
        form = GuardianLinkForm(
            data={"student": self.student.pk, "guardian": new_parent.pk},
            guardian_queryset=get_user_model().objects.filter(pk__in=[self.parent_user.pk, new_parent.pk]),
        )
        self.assertTrue(form.is_valid())
        student, guardian, already_linked = form.save()
        self.assertFalse(already_linked)
        self.assertEqual(student, self.student)
        self.assertEqual(guardian, new_parent)
        self.assertIn(new_parent, self.student.guardians.all())

    def test_guardian_link_form_defaults_include_all_users(self) -> None:
        form = GuardianLinkForm()
        guardian_field = form.fields["guardian"]
        student_field = form.fields["student"]
        self.assertIsNone(guardian_field.empty_label)
        self.assertIsNone(student_field.empty_label)
        guardians = list(guardian_field.queryset)
        self.assertIn(self.parent_user, guardians)
        self.assertIn(self.teacher_user, guardians)

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


class RegistrationTests(TestCase):
    @patch("crm.forms.generate_verification_code", return_value="654321")
    def test_parent_registration_creates_user_with_parent_group(self, code_generator) -> None:
        with self.assertLogs("crm.views", level="INFO") as log_capture:
            response = self.client.post(
                reverse("crm:parent_register"),
                {
                    "first_name": "Мария",
                    "last_name": "Иванова",
                    "phone_number": "+7 (999) 000-00-00",
                },
            )
        self.assertRedirects(response, reverse("login"))
        user_model = get_user_model()
        user = user_model.objects.get(username="+79990000000")
        self.assertTrue(user.check_password("654321"))
        self.assertEqual(user.first_name, "Мария")
        self.assertEqual(user.last_name, "Иванова")
        parent_group = Group.objects.get(name="Родители")
        self.assertIn(parent_group, user.groups.all())
        self.assertTrue(any("654321" in message for message in log_capture.output))

    def test_parent_registration_validates_unique_phone(self) -> None:
        user_model = get_user_model()
        user_model.objects.create_user(username="+79990000000", password="testpass123")
        response = self.client.post(
            reverse("crm:parent_register"),
            {
                "first_name": "Мария",
                "last_name": "Иванова",
                "phone_number": "+7 (999) 000-00-00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пользователь с таким номером уже зарегистрирован.")

