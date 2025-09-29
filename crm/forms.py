from django import forms
from django.contrib.auth import get_user_model

from .models import Course, Enrollment, Exercise, Lesson, Payment, Student, Subscription


class DateInput(forms.DateInput):
    input_type = "date"


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ["course", "date", "topic"]
        widgets = {"date": DateInput()}


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "description", "schedule", "capacity", "teacher"]


class StudentForm(forms.ModelForm):
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
        self.fields["courses"].queryset = Course.objects.order_by("title")


class EnrollmentForm(forms.ModelForm):
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


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = [
            "student",
            "course",
            "lessons_included",
            "price",
            "start_date",
            "end_date",
            "is_active",
        ]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}


class PaymentForm(forms.ModelForm):
    paid_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = Payment
        fields = ["student", "subscription", "amount", "paid_at", "method", "comment"]


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ["title", "description", "order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }
