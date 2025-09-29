from django import forms

from .models import Course, Lesson, Payment, Subscription


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
