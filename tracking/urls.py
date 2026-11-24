from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("log/", views.my_log, name="my_log"),
    path("my-summary/", views.my_summary, name="my_summary"),
    path("entries/<int:pk>/edit/", views.entry_edit, name="entry_edit"),
    path("entries/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("records/", views.records, name="records"),
    path("interns/<int:pk>/", views.intern_detail, name="intern_detail"),
    path("review/", views.review_queue, name="review_queue"),
    path("review/<int:pk>/reviewed/", views.mark_reviewed, name="mark_reviewed"),
]
