from django.urls import path

from . import views

urlpatterns = [path("", views.upload_workbook, name="import_workbook")]
