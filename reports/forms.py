from django import forms

from tracking.forms import DateRangeForm
from tracking.models import InternProfile


class ReportForm(DateRangeForm):
    SCOPE_CHOICES = [("all", "All interns"), ("intern", "One intern")]
    FORMAT_CHOICES = [("xlsx", "Excel, with a summary sheet"), ("csv", "CSV, entries only")]

    scope = forms.ChoiceField(choices=SCOPE_CHOICES, initial="all", widget=forms.RadioSelect)
    intern = forms.ModelChoiceField(queryset=InternProfile.objects.all(), required=False)
    file_format = forms.ChoiceField(
        choices=FORMAT_CHOICES, initial="xlsx", label="Format", widget=forms.RadioSelect
    )
    include_excluded = forms.BooleanField(
        required=False,
        label="Include interns excluded from the summary",
        help_text="Applies to all-intern reports.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("scope") == "intern" and not cleaned.get("intern"):
            self.add_error("intern", "Choose an intern.")
        return cleaned
