from django.contrib import admin

from . import models


@admin.register(models.Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "guardian_phone", "created_at")
    filter_horizontal = ("guardians",)
    search_fields = ("last_name", "first_name", "guardian_phone", "guardians__username")
    list_filter = ("created_at",)


@admin.register(models.Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "schedule", "start_date", "end_date")
    search_fields = ("title", "teacher__username", "teacher__first_name", "teacher__last_name")
    list_filter = ("teacher", "created_at")


@admin.register(models.Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "start_date", "is_active")
    list_filter = ("course", "is_active")
    search_fields = ("student__last_name", "course__title")


@admin.register(models.Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("course", "date", "topic")
    list_filter = ("course", "date")
    search_fields = ("course__title", "topic")


@admin.register(models.Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("lesson", "student", "status", "comment")
    list_filter = ("lesson__course", "status")
    search_fields = ("student__last_name", "lesson__course__title")


@admin.register(models.Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("lesson", "title", "order")
    list_filter = ("lesson__course",)
    search_fields = ("title", "lesson__course__title")


@admin.register(models.ExerciseResult)
class ExerciseResultAdmin(admin.ModelAdmin):
    list_display = ("exercise", "student", "status", "comment")
    list_filter = ("status", "exercise__lesson__course")
    search_fields = ("student__last_name", "exercise__title")



@admin.register(models.Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "lessons_included", "price", "purchase_date", "is_active")
    list_filter = ("course", "is_active", "purchase_date")
    search_fields = ("student__last_name", "course__title")

