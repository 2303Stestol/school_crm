import os
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm import models
from crm.forms import EnrollmentForm, GuardianLinkForm, SubscriptionForm


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

    def test_lessons_balance_ignores_future_lessons(self) -> None:
        today = timezone.localdate()
        future_day = today + timedelta(days=7)
        models.Subscription.objects.create(
            student=self.student,
            course=self.course,
            lessons_included=1,
            price=3000,
            purchase_date=today,
        )
        past_lesson = models.Lesson.objects.create(
            course=self.course,
            date=today,
        )
        future_lesson = models.Lesson.objects.create(
            course=self.course,
            date=future_day,
        )
        models.Attendance.objects.create(
            lesson=past_lesson,
            student=self.student,
            status=models.AttendanceStatus.PRESENT,
        )
        models.Attendance.objects.create(
            lesson=future_lesson,
            student=self.student,
            status=models.AttendanceStatus.PRESENT,
        )
        balance = self.student.lessons_balance()
        self.assertEqual(balance["billable"], 1)
        self.assertEqual(balance["debt"], 0)

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

    def test_course_schedule_display(self) -> None:
        course = models.Course.objects.create(
            title="Алгебра",
            description="",
            schedule="mon,wed,fri",
            teacher=self.teacher_user,
        )
        self.assertEqual(course.schedule_days, ["mon", "wed", "fri"])
        self.assertEqual(course.schedule_display(), "Понедельник, Среда, Пятница")

    def test_generate_lessons_for_course_creates_schedule(self) -> None:
        created = models.generate_lessons_for_course(
            self.course,
            ["mon", "wed"],
            start_date=date(2024, 1, 1),
            weeks_ahead=1,
        )
        self.assertEqual(created, 3)
        self.assertTrue(
            models.Lesson.objects.filter(course=self.course, date=date(2024, 1, 1)).exists()
        )
        self.assertTrue(
            models.Lesson.objects.filter(course=self.course, date=date(2024, 1, 3)).exists()
        )
        self.assertTrue(
            models.Lesson.objects.filter(course=self.course, date=date(2024, 1, 8)).exists()
        )
        duplicate = models.generate_lessons_for_course(
            self.course,
            ["mon"],
            start_date=date(2024, 1, 1),
            weeks_ahead=0,
        )
        self.assertEqual(duplicate, 0)

    def test_subscription_form_requires_enrollment(self) -> None:
        enrolled_student = self.student
        another_student = models.Student.objects.create(
            first_name="Анна",
            last_name="Петрова",
        )
        models.Enrollment.objects.create(
            student=enrolled_student,
            course=self.course,
            start_date=date(2024, 1, 1),
        )
        other_course = models.Course.objects.create(
            title="Физика",
            description="",
            teacher=self.teacher_user,
        )
        models.Enrollment.objects.create(
            student=another_student,
            course=other_course,
            start_date=date(2024, 1, 1),
        )

        form_prefilled = SubscriptionForm(initial={"course": self.course.pk})
        self.assertIn(enrolled_student, form_prefilled.fields["student"].queryset)
        self.assertNotIn(another_student, form_prefilled.fields["student"].queryset)

        form = SubscriptionForm(
            data={
                "student": another_student.pk,
                "course": self.course.pk,
                "lessons_included": "4",
                "price": "4000",
                "purchase_date": "2024-01-01",
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("корректный вариант", form.errors["student"][0].lower())

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
        with tempfile.TemporaryDirectory() as tmp_dir:
            codes_path = os.path.join(tmp_dir, "codes.log")
            with override_settings(VERIFICATION_CODES_FILE=codes_path):
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
                self.assertTrue(os.path.exists(codes_path))
                with open(codes_path, "r", encoding="utf-8") as stored:
                    saved_codes = stored.read()
                self.assertIn("+79990000000", saved_codes)
                self.assertIn("654321", saved_codes)

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


class LoginTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.phone_number = "+79990000000"
        self.user = self.user_model.objects.create_user(
            username=self.phone_number,
            password="initialpass123",
            first_name="Мария",
        )

    def _login_url(self) -> str:
        return reverse("login")

    def _dashboard_url(self) -> str:
        return reverse("crm:dashboard")

    @patch("crm.views.generate_verification_code", return_value="111222")
    def test_login_request_generates_code_and_updates_password(self, code_generator) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codes_path = os.path.join(tmp_dir, "codes.log")
            with override_settings(VERIFICATION_CODES_FILE=codes_path):
                response = self.client.post(
                    self._login_url(),
                    {"phone_number": "+7 (999) 000-00-00"},
                )
                self.assertRedirects(response, self._login_url())
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password("111222"))
                with open(codes_path, "r", encoding="utf-8") as stored:
                    saved_codes = stored.read()
                self.assertIn(self.phone_number, saved_codes)
                self.assertIn("111222", saved_codes)

    @patch("crm.views.generate_verification_code", return_value="333444")
    def test_login_with_correct_code_logs_user_in(self, code_generator) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codes_path = os.path.join(tmp_dir, "codes.log")
            with override_settings(VERIFICATION_CODES_FILE=codes_path):
                self.client.post(
                    self._login_url(),
                    {"phone_number": "+7 (999) 000-00-00"},
                )
                response = self.client.post(
                    self._login_url(),
                    {"phone_number": "+7 (999) 000-00-00", "code": "333444"},
                )
                self.assertRedirects(response, self._dashboard_url())
                self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    @patch("crm.views.generate_verification_code", return_value="555666")
    def test_login_with_wrong_code_shows_error(self, code_generator) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codes_path = os.path.join(tmp_dir, "codes.log")
            with override_settings(VERIFICATION_CODES_FILE=codes_path):
                self.client.post(
                    self._login_url(),
                    {"phone_number": "+7 (999) 000-00-00"},
                )
                response = self.client.post(
                    self._login_url(),
                    {"phone_number": "+7 (999) 000-00-00", "code": "000000"},
                    follow=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Неверный код")

    def test_login_with_unknown_phone_shows_error(self) -> None:
        response = self.client.post(
            self._login_url(),
            {"phone_number": "+7 (888) 000-00-00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пользователь с таким номером не найден.")
