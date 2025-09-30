import random
import re

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist

from .models import (
    Course,
    Enrollment,
    Exercise,
    Lesson,
    Student,
    Subscription,
    WEEKDAY_CHOICES,
    WEEKDAY_TO_INDEX,
)

PARENT_GROUP_NAME = "Родители"


def generate_verification_code(length: int = 6) -> str:
    """Return a numeric verification code used as a temporary password."""

    digits = "0123456789"
    return "".join(random.choice(digits) for _ in range(length))


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize a phone number to +79990000000 format."""

    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) < 10:
        raise forms.ValidationError("Введите корректный номер телефона.")
    return f"+{digits}"


def _guardian_label(user) -> str:
    """Return a readable label for guardian selections."""

    full_name = (user.get_full_name() or "").strip()
    username = user.get_username()
    email = getattr(user, "email", "") or ""

    if full_name:
        if username and username not in full_name:
            return f"{full_name} ({username})"
        return full_name
    if username:
        return username
    if email:
        return email
    return f"Пользователь #{user.pk}"


def _user_ordering(user_model) -> list[str]:
    ordering: list[str] = []
    for field_name in ("last_name", "first_name"):
        try:
            user_model._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue
        ordering.append(field_name)
    username_field = getattr(user_model, "USERNAME_FIELD", "username")
    if username_field and username_field not in ordering:
        ordering.append(username_field)
    if not ordering:
        ordering.append("pk")
    return ordering



class LiveSearchMixin:
    live_search_fields: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.live_search_fields:
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs.setdefault("data-live-search", "true")
                if isinstance(field, forms.ModelChoiceField):
                    field.empty_label = ""


class DateInput(forms.DateInput):
    input_type = "date"


class LessonForm(LiveSearchMixin, forms.ModelForm):
    live_search_fields = ("course",)

    class Meta:
        model = Lesson
        fields = ["course", "date", "topic"]
        widgets = {"date": DateInput()}


class CourseForm(LiveSearchMixin, forms.ModelForm):
    live_search_fields = ("teacher",)
    schedule_days = forms.MultipleChoiceField(
        label="Дни занятий",
        required=False,
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Выберите дни недели, чтобы автоматически создавать будущие занятия.",
    )

    class Meta:
        model = Course
        fields = ["title", "description", "capacity", "teacher"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["schedule_days"].initial = self.instance.schedule_days

    def save(self, commit: bool = True):
        instance: Course = super().save(commit=False)
        schedule_days = self.cleaned_data.get("schedule_days") or []
        ordered = sorted(schedule_days, key=lambda value: WEEKDAY_TO_INDEX.get(value, 0))
        instance.schedule = ",".join(ordered)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StudentForm(LiveSearchMixin, forms.ModelForm):
    live_search_fields = ("guardians",)

    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        required=False,
        label="Записать на курсы",
        help_text="Выберите курсы, на которые нужно сразу записать ученика.",
    )

    class Meta:
        model = Student
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "birth_date",
            "guardian_name",
            "guardian_phone",
            "guardians",
            "notes",
        ]
        widgets = {
            "birth_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["guardians"].queryset = get_user_model().objects.order_by("username")
        self.fields["guardians"].required = False
        self.fields["guardians"].label_from_instance = _guardian_label
        self.fields["courses"].queryset = Course.objects.order_by("title")
        self.fields["courses"].widget.attrs.setdefault("data-live-search", "true")


class EnrollmentForm(LiveSearchMixin, forms.ModelForm):
    live_search_fields = ("student", "course")

    class Meta:
        model = Enrollment
        fields = ["student", "course", "start_date", "end_date", "is_active"]
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.order_by("last_name", "first_name")
        self.fields["course"].queryset = Course.objects.order_by("title")

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        course = cleaned_data.get("course")
        is_active = cleaned_data.get("is_active")
        if not student or not course:
            return cleaned_data
        existing = Enrollment.objects.filter(student=student, course=course)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if is_active and existing.filter(is_active=True).exists():
            raise forms.ValidationError(
                "У этого ученика уже есть активная запись на выбранный курс."
            )
        return cleaned_data


class SubscriptionForm(LiveSearchMixin, forms.ModelForm):
    live_search_fields = ("student", "course")

    class Meta:
        model = Subscription
        fields = [
            "student",
            "course",
            "lessons_included",
            "price",
            "purchase_date",
            "is_active",
        ]
        widgets = {"purchase_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = Course.objects.order_by("title")
        self.fields["student"].queryset = Student.objects.none()
        selected_course = None
        if self.data.get("course"):
            try:
                selected_course = int(self.data.get("course"))
            except (TypeError, ValueError):
                selected_course = None
        elif self.initial.get("course"):
            initial_course = self.initial.get("course")
            if isinstance(initial_course, Course):
                selected_course = initial_course.pk
            else:
                selected_course = initial_course
        if selected_course:
            self.fields["student"].queryset = (
                Student.objects.filter(
                    enrollments__course_id=selected_course,
                    enrollments__is_active=True,
                )
                .order_by("last_name", "first_name")
                .distinct()
            )
        else:
            self.fields["student"].help_text = "Сначала выберите курс, чтобы выбрать ученика."

    def clean_student(self):
        student = self.cleaned_data.get("student")
        course = self.cleaned_data.get("course")
        if student and course:
            exists = Enrollment.objects.filter(
                student=student,
                course=course,
                is_active=True,
            ).exists()
            if not exists:
                raise forms.ValidationError(
                    "Ученик не записан на выбранный курс. Выберите другого ученика."
                )
        return student


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ["title", "description", "order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class GuardianLinkForm(LiveSearchMixin, forms.Form):
    live_search_fields = ("student", "guardian")

    student = forms.ModelChoiceField(
        queryset=Student.objects.none(), label="Ученик"
    )
    guardian = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), label="Родитель"
    )

    def __init__(
        self,
        *args,
        student_queryset=None,
        guardian_queryset=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if student_queryset is None:
            student_queryset = Student.objects.order_by("last_name", "first_name")

        self.fields["student"].queryset = student_queryset
        self.fields["student"].empty_label = None

        user_model = get_user_model()
        if guardian_queryset is None:
            guardian_queryset = (
                user_model.objects.order_by(*_user_ordering(user_model)).distinct()
            )

        self.fields["guardian"].queryset = guardian_queryset
        self.fields["guardian"].empty_label = None
        self.fields["guardian"].label_from_instance = _guardian_label
        self.fields["student"].label_from_instance = lambda student: student.full_name or str(student)

    def save(self):
        student: Student = self.cleaned_data["student"]
        guardian = self.cleaned_data["guardian"]
        already_linked = student.guardians.filter(pk=guardian.pk).exists()
        if not already_linked:
            student.guardians.add(guardian)
        return student, guardian, already_linked


class ParentRegistrationForm(forms.Form):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)
    phone_number = forms.CharField(label="Номер телефона", max_length=32)

    def clean_phone_number(self):
        normalized = normalize_phone_number(self.cleaned_data["phone_number"])
        user_model = get_user_model()
        username_field = getattr(user_model, "USERNAME_FIELD", "username") or "username"
        if user_model._default_manager.filter(**{username_field: normalized}).exists():
            raise forms.ValidationError("Пользователь с таким номером уже зарегистрирован.")
        return normalized

    def save(self):
        user_model = get_user_model()
        username_field = getattr(user_model, "USERNAME_FIELD", "username") or "username"
        password = generate_verification_code()
        create_kwargs = {
            username_field: self.cleaned_data["phone_number"],
            "first_name": self.cleaned_data["first_name"],
            "last_name": self.cleaned_data["last_name"],
            "password": password,
        }
        user = user_model.objects.create_user(**create_kwargs)
        return user, password


class PhoneLoginForm(forms.Form):
    phone_number = forms.CharField(label="Номер телефона", max_length=32)
    code = forms.CharField(
        label="Код подтверждения",
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code"}),
    )

    error_messages = {
        "invalid_phone": "Введите корректный номер телефона.",
        "user_not_found": "Пользователь с таким номером не найден.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_cache = None

    def clean_phone_number(self):
        try:
            normalized = normalize_phone_number(self.cleaned_data["phone_number"])
        except forms.ValidationError as error:
            raise forms.ValidationError(self.error_messages["invalid_phone"]) from error
        user_model = get_user_model()
        username_field = getattr(user_model, "USERNAME_FIELD", "username") or "username"
        user = user_model._default_manager.filter(**{username_field: normalized}).first()
        if user is None:
            raise forms.ValidationError(self.error_messages["user_not_found"])
        self.user_cache = user
        return normalized

    def get_user(self):
        return self.user_cache

