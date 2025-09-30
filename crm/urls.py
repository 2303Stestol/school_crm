from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("courses/create/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("lessons/create/", views.lesson_create, name="lesson_create"),
    path("lessons/<int:pk>/", views.lesson_manage, name="lesson_manage"),
    path("students/create/", views.student_create, name="student_create"),
    path("students/link-guardian/", views.student_guardian_link, name="student_guardian_link"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("enrollments/create/", views.enrollment_create, name="enrollment_create"),
    path("subscriptions/create/", views.subscription_create, name="subscription_create"),
]
