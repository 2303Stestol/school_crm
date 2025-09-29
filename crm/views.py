from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.forms import modelformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CourseForm,
    EnrollmentForm,
    LessonForm,
    PaymentForm,
    StudentForm,
    SubscriptionForm,
)
from .models import (
    Attendance,
    Course,
    Enrollment,
    Lesson,
    LessonTaskStatus,
    Payment,
    Student,
    Subscription,
)


ADMIN_GROUP = "Администраторы"
TEACHER_GROUP = "Учителя"
PARENT_GROUP = "Родители"


def is_admin(user) -> bool:
    return user.is_superuser or user.groups.filter(name=ADMIN_GROUP).exists()


def is_teacher(user) -> bool:
    return user.groups.filter(name=TEACHER_GROUP).exists()


def is_parent(user) -> bool:
    return user.groups.filter(name=PARENT_GROUP).exists()


def _forbidden() -> HttpResponseForbidden:
    return HttpResponseForbidden("Недостаточно прав для выполнения действия")


@login_required
def dashboard(request):
    user = request.user
    context: dict[str, object]
    if is_admin(user):
        context = {
            "role": "admin",
            "courses": Course.objects.select_related("teacher").order_by("title"),
            "students": Student.objects.prefetch_related("guardians").order_by("last_name"),
            "recent_payments": Payment.objects.select_related("student").order_by("-paid_at")[:5],
            "recent_subscriptions": Subscription.objects.select_related("student", "course")
            .order_by("-start_date")[:5],
        }
    elif is_teacher(user):
        context = {
            "role": "teacher",
            "courses": Course.objects.filter(teacher=user)
            .prefetch_related(
                Prefetch(
                    "lessons",
                    queryset=Lesson.objects.order_by("-date"),
                )
            )
            .order_by("title"),
        }
    elif is_parent(user):
        context = {
            "role": "parent",
            "students": user.students.prefetch_related(
                Prefetch(
                    "attendances",
                    queryset=Attendance.objects.select_related("lesson", "lesson__course").order_by(
                        "-lesson__date"
                    ),
                ),
                Prefetch(
                    "subscriptions",
                    queryset=Subscription.objects.select_related("course").order_by("-start_date"),
                ),
            ).order_by("last_name"),
        }
    else:
        context = {"role": "guest"}
    return render(request, "crm/dashboard.html", context)


def _can_manage_course(user, course: Course) -> bool:
    return is_admin(user) or (is_teacher(user) and course.teacher_id == user.id)


@login_required
def course_detail(request, pk: int):
    course = get_object_or_404(
        Course.objects.select_related("teacher").prefetch_related(
            Prefetch("lessons", queryset=Lesson.objects.order_by("-date")),
            Prefetch(
                "enrollments",
                queryset=Enrollment.objects.select_related("student").order_by("student__last_name"),
            ),
        ),
        pk=pk,
    )
    if not _can_manage_course(request.user, course) and not is_parent(request.user):
        return _forbidden()
    if is_parent(request.user) and not course.enrollments.filter(
        student__guardians=request.user
    ).exists():
        return _forbidden()
    return render(
        request,
        "crm/course_detail.html",
        {
            "course": course,
            "enrollments": course.enrollments.all(),
            "lessons": course.lessons.all(),
            "can_edit": _can_manage_course(request.user, course),
            "can_manage_enrollments": is_admin(request.user),
        },
    )


@login_required
def lesson_create(request):
    user = request.user
    if not (is_teacher(user) or is_admin(user)):
        return _forbidden()
    form = LessonForm(request.POST or None)
    if is_teacher(user) and not is_admin(user):
        form.fields["course"].queryset = Course.objects.filter(teacher=user)
    if request.method != "POST":
        course_id = request.GET.get("course")
        if course_id:
            form.initial["course"] = course_id
    if request.method == "POST" and form.is_valid():
        lesson = form.save()
        messages.success(request, "Занятие создано")
        return redirect("crm:lesson_manage", pk=lesson.pk)
    return render(request, "crm/lesson_form.html", {"form": form})


@login_required
def lesson_manage(request, pk: int):
    lesson = get_object_or_404(
        Lesson.objects.select_related("course", "course__teacher"),
        pk=pk,
    )
    if not _can_manage_course(request.user, lesson.course):
        return _forbidden()

    enrollments = (
        lesson.course.enrollments.filter(is_active=True)
        .filter(Q(start_date__lte=lesson.date), Q(end_date__isnull=True) | Q(end_date__gte=lesson.date))
        .select_related("student")
        .order_by("student__last_name")
    )
    for enrollment in enrollments:
        Attendance.objects.get_or_create(lesson=lesson, student=enrollment.student)

    AttendanceFormSet = modelformset_factory(
        Attendance,
        fields=("status", "task_status", "comment"),
        extra=0,
    )
    queryset = Attendance.objects.filter(lesson=lesson).select_related("student").order_by(
        "student__last_name"
    )

    if request.method == "POST":
        formset = AttendanceFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Посещаемость сохранена")
            return redirect("crm:lesson_manage", pk=lesson.pk)
    else:
        formset = AttendanceFormSet(queryset=queryset)

    return render(
        request,
        "crm/lesson_manage.html",
        {
            "lesson": lesson,
            "course": lesson.course,
            "formset": formset,
            "task_status_choices": LessonTaskStatus,
        },
    )


@login_required
def student_detail(request, pk: int):
    student = get_object_or_404(
        Student.objects.prefetch_related(
            Prefetch(
                "attendances",
                queryset=Attendance.objects.select_related("lesson", "lesson__course").order_by(
                    "-lesson__date"
                ),
            ),
            Prefetch(
                "subscriptions",
                queryset=Subscription.objects.select_related("course").order_by("-start_date"),
            ),
            Prefetch("payments", queryset=Payment.objects.order_by("-paid_at")),
        ),
        pk=pk,
    )
    user = request.user
    if is_parent(user) and not student.guardians.filter(pk=user.pk).exists():
        return _forbidden()
    if is_teacher(user) and not Enrollment.objects.filter(course__teacher=user, student=student).exists():
        return _forbidden()
    if not (is_admin(user) or is_teacher(user) or is_parent(user)):
        return _forbidden()

    return render(
        request,
        "crm/student_detail.html",
        {
            "student": student,
            "attendances": student.attendances.all(),
            "subscriptions": student.subscriptions.all(),
            "payments": student.payments.all(),
        },
    )


@login_required
def course_create(request):
    if not is_admin(request.user):
        return _forbidden()
    form = CourseForm(request.POST or None)
    form.fields["teacher"].queryset = get_user_model().objects.filter(groups__name=TEACHER_GROUP)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        messages.success(request, "Курс создан")
        return redirect("crm:course_detail", pk=course.pk)
    return render(request, "crm/course_form.html", {"form": form})


@login_required
def student_create(request):
    if not is_admin(request.user):
        return _forbidden()
    form = StudentForm(request.POST or None)
    course_id = request.GET.get("course")
    if course_id and request.method != "POST":
        form.fields["courses"].initial = Course.objects.filter(pk=course_id)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        form.save_m2m()
        courses = form.cleaned_data.get("courses") or []
        for course in courses:
            Enrollment.objects.get_or_create(
                student=student,
                course=course,
                defaults={"start_date": timezone.now().date()},
            )
        messages.success(request, "Ученик создан")
        if course_id:
            return redirect("crm:course_detail", pk=course_id)
        return redirect("crm:student_detail", pk=student.pk)
    return render(request, "crm/student_form.html", {"form": form})


@login_required
def enrollment_create(request):
    if not is_admin(request.user):
        return _forbidden()
    form = EnrollmentForm(request.POST or None)
    course_id = request.GET.get("course")
    if course_id:
        course = Course.objects.filter(pk=course_id).first()
        if course:
            form.fields["course"].queryset = Course.objects.filter(pk=course_id)
            if request.method != "POST":
                form.fields["course"].initial = course
    if request.method == "POST" and form.is_valid():
        enrollment = form.save()
        messages.success(request, "Ученик записан на курс")
        return redirect("crm:course_detail", pk=enrollment.course_id)
    return render(request, "crm/enrollment_form.html", {"form": form})


@login_required
def subscription_create(request):
    if not is_admin(request.user):
        return _forbidden()
    form = SubscriptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        subscription = form.save()
        messages.success(request, "Абонемент сохранён")
        return redirect("crm:student_detail", pk=subscription.student_id)
    return render(request, "crm/subscription_form.html", {"form": form})


@login_required
def payment_create(request):
    if not is_admin(request.user):
        return _forbidden()
    form = PaymentForm(request.POST or None)
    if request.method != "POST":
        form.initial.setdefault("paid_at", timezone.now().strftime("%Y-%m-%dT%H:%M"))
    if request.method == "POST" and form.is_valid():
        payment = form.save()
        messages.success(request, "Платёж сохранён")
        return redirect("crm:student_detail", pk=payment.student_id)
    return render(request, "crm/payment_form.html", {"form": form})
