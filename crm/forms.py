from django import forms
from django.contrib.auth import get_user_model

from .models import Course, Enrollment, Exercise, Lesson, Student, Subscription


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



class LiveSearchMixin:
    live_search_fields: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.live_search_fields:
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs.setdefault("data-live-search", "true")


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

    class Meta:
        model = Course
        fields = ["title", "description", "schedule", "capacity", "teacher"]


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

    def __init__(self, *args, **kwargs):
        guardian_queryset = kwargs.pop("guardian_queryset", None)
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.order_by("last_name", "first_name")
        if guardian_queryset is None:
            guardian_queryset = get_user_model().objects.order_by("username")
        self.fields["guardian"].queryset = guardian_queryset
        self.fields["guardian"].label_from_instance = _guardian_label

    def save(self):
        student: Student = self.cleaned_data["student"]
        guardian = self.cleaned_data["guardian"]
        already_linked = student.guardians.filter(pk=guardian.pk).exists()
        if not already_linked:
            student.guardians.add(guardian)
        return student, guardian, already_linked

