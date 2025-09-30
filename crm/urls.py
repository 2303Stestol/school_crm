from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("accounts/register/", views.parent_register, name="parent_register"),
    path("", views.dashboard, name="dashboard"),
    path("courses/create/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("lessons/create/", views.lesson_create, name="lesson_create"),
    path("lessons/<int:pk>/edit/", views.lesson_update, name="lesson_update"),
    path("lessons/<int:pk>/delete/", views.lesson_delete, name="lesson_delete"),
    path("lessons/<int:pk>/", views.lesson_manage, name="lesson_manage"),
    path("exercises/<int:pk>/edit/", views.exercise_update, name="exercise_update"),
    path("exercises/<int:pk>/delete/", views.exercise_delete, name="exercise_delete"),
    path("students/create/", views.student_create, name="student_create"),
    path("students/link-guardian/", views.student_guardian_link, name="student_guardian_link"),
    path("roles/assign/", views.assign_role, name="assign_role"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("enrollments/create/", views.enrollment_create, name="enrollment_create"),
    path("subscriptions/create/", views.subscription_create, name="subscription_create"),
]
