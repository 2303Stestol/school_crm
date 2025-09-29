from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Prefetch, Q
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CourseForm,
    ExerciseForm,
    EnrollmentForm,
    LessonForm,
    PaymentForm,
    StudentForm,
    SubscriptionForm,
)
from .models import (
    Attendance,
    AttendanceStatus,
    Course,
    Enrollment,
    Exercise,
    ExerciseResult,
    ExerciseStatus,
    Lesson,
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
        students = list(
            user.students.prefetch_related(
                Prefetch(
                    "attendances",
                    queryset=
                    Attendance.objects.select_related("lesson", "lesson__course")
                    .prefetch_related("lesson__exercises")
                    .order_by("-lesson__date"),
                ),
                Prefetch(
                    "subscriptions",
                    queryset=Subscription.objects.select_related("course").order_by("-start_date"),
                ),
            ).order_by("last_name")
        )
        for student in students:
            _attach_results_for_student(student)
        context = {
            "role": "parent",
            "students": students,
        }
    else:
        context = {"role": "guest"}
    return render(request, "crm/dashboard.html", context)


def _can_manage_course(user, course: Course) -> bool:
    return is_admin(user) or (is_teacher(user) and course.teacher_id == user.id)


def _attach_results_for_student(student: Student) -> None:
    attendances = list(student.attendances.all())
    if not attendances:
        return
    lesson_ids = {attendance.lesson_id for attendance in attendances}
    results = (
        ExerciseResult.objects.filter(student=student, exercise__lesson_id__in=lesson_ids)
        .select_related("exercise")
        .order_by("exercise__order", "exercise__created_at")
    )
    by_lesson: dict[int, list[ExerciseResult]] = {}
    for result in results:
        by_lesson.setdefault(result.exercise.lesson_id, []).append(result)
    for attendance in attendances:
        attendance.set_prefetched_results(by_lesson.get(attendance.lesson_id, []))


@login_required
def course_detail(request, pk: int):
    course = get_object_or_404(
        Course.objects.select_related("teacher").prefetch_related(
            Prefetch(
                "lessons",
                queryset=Lesson.objects.prefetch_related("exercises").order_by("-date"),
            ),
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
        Lesson.objects.select_related("course", "course__teacher")
        .prefetch_related("exercises"),
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
    students = [enrollment.student for enrollment in enrollments]
    attendances = [
        Attendance.objects.get_or_create(lesson=lesson, student=enrollment.student)[0]
        for enrollment in enrollments
    ]

    exercises = list(lesson.exercises.order_by("order", "created_at"))
    for exercise in exercises:
        for student in students:
            ExerciseResult.objects.get_or_create(exercise=exercise, student=student)

    result_lookup: dict[int, dict[int, ExerciseResult]] = {}
    result_queryset = (
        ExerciseResult.objects.filter(exercise__lesson=lesson, student__in=students)
        .select_related("exercise", "student")
    )
    for res in result_queryset:
        result_lookup.setdefault(res.student_id, {})[res.exercise_id] = res

    if request.method == "POST" and request.POST.get("action") == "add_exercise":
        exercise_form = ExerciseForm(request.POST, prefix="exercise")
        if exercise_form.is_valid():
            new_exercise = exercise_form.save(commit=False)
            new_exercise.lesson = lesson
            if new_exercise.order == 0:
                new_exercise.order = (lesson.exercises.aggregate(Max("order"))["order__max"] or 0) + 1
            new_exercise.save()
            messages.success(request, "Упражнение добавлено")
            return redirect("crm:lesson_manage", pk=lesson.pk)
    elif request.method == "POST":
        exercise_form = ExerciseForm(prefix="exercise")
        status_choices = {choice[0] for choice in AttendanceStatus.choices}
        exercise_choices = {choice[0] for choice in ExerciseStatus.choices}
        with transaction.atomic():
            for attendance in attendances:
                status_key = f"attendance-status-{attendance.student_id}"
                comment_key = f"attendance-comment-{attendance.student_id}"
                status_value = request.POST.get(status_key)
                if status_value in status_choices:
                    attendance.status = status_value
                attendance.comment = request.POST.get(comment_key, "")
                attendance.save()
            for exercise in exercises:
                for student in students:
                    result = result_lookup.get(student.id, {}).get(exercise.id)
                    if result is None:
                        result = ExerciseResult.objects.get(exercise=exercise, student=student)
                        result_lookup.setdefault(student.id, {})[exercise.id] = result
                    key = f"exercise-{exercise.id}-student-{student.id}"
                    status_value = request.POST.get(key)
                    if status_value in exercise_choices:
                        result.status = status_value
                    result.comment = request.POST.get(f"{key}-comment", "")
                    result.save()
        messages.success(request, "Данные по занятию сохранены")
        return redirect("crm:lesson_manage", pk=lesson.pk)
    else:
        exercise_form = ExerciseForm(prefix="exercise")

    return render(
        request,
        "crm/lesson_manage.html",
        {
            "lesson": lesson,
            "course": lesson.course,
            "attendances": attendances,
            "students": students,
            "exercises": exercises,
            "result_lookup": result_lookup,
            "attendance_statuses": AttendanceStatus.choices,
            "exercise_statuses": ExerciseStatus.choices,
            "exercise_form": exercise_form,
            "table_columns": 3 + max(len(exercises), 1),
        },
    )


@login_required
def student_detail(request, pk: int):
    student = get_object_or_404(
        Student.objects.prefetch_related(
            Prefetch(
                "attendances",
                queryset=
                Attendance.objects.select_related("lesson", "lesson__course")
                .prefetch_related("lesson__exercises")
                .order_by("-lesson__date"),
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

    _attach_results_for_student(student)

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
