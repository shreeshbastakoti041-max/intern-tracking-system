from django.shortcuts import render

from accounts.permissions import supervisor_or_admin_required
from tracking.models import TimeEntry

from . import builders
from .forms import ReportForm


@supervisor_or_admin_required
def report_builder(request):
    form = ReportForm(request.GET or None, initial={"scope": "all", "file_format": "xlsx"})
    if request.GET.get("download") and form.is_valid():
        start, end, _ = form.get_range(default_key="all")
        data = form.cleaned_data
        qs = TimeEntry.objects.visible_to(request.user).in_range(start, end)
        if data["scope"] == "intern":
            profile = data["intern"]
            qs = qs.filter(intern=profile)
            if data["file_format"] == "csv":
                stem = f"{profile.display_name}-entries"
                return builders.entries_csv_response(qs, stem, start, end)
            return builders.intern_report_response(profile, qs, start, end, request.user)
        if not data["include_excluded"]:
            qs = qs.filter(intern__include_in_summary=True)
        if data["file_format"] == "csv":
            return builders.entries_csv_response(qs, "all-interns-entries", start, end)
        return builders.all_interns_report_response(qs, start, end, request.user)
    return render(request, "reports/report_form.html", {"form": form})
