from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "OSP Intern Tracker administration"
admin.site.site_title = "OSP Intern Tracker"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("demo/", include("accounts.demo_urls")),
    path("reports/", include("reports.urls")),
    path("import/", include("imports.urls")),
    path("", include("tracking.urls")),
]
