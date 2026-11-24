from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import TaskCategory, TimeEntry, WorkUnit
from .services.hours import duration_hours, overlaps
from .services.periods import current_quarter_key, presets


class TimeEntryForm(forms.ModelForm):
    """Interns log one task per entry. Hours are always computed from start/end."""

    class Meta:
        model = TimeEntry
        fields = [
            "date",
            "start_time",
            "end_time",
            "work_unit",
            "task_category",
            "description",
            "is_backlog",
            "ai_used",
            "supervisor",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "description": forms.TextInput(attrs={"placeholder": "e.g. Proposal routing review"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, intern, **kwargs):
        super().__init__(*args, **kwargs)
        self.intern = intern
        for name in ("date", "start_time", "end_time", "work_unit", "description"):
            self.fields[name].required = True

        # Show active choices, plus the entry's current value if it has since been retired.
        current = self.instance if self.instance.pk else None
        units = WorkUnit.objects.filter(is_active=True)
        cats = TaskCategory.objects.filter(is_active=True)
        if current and current.work_unit_id:
            units = units | WorkUnit.objects.filter(pk=current.work_unit_id)
        if current and current.task_category_id:
            cats = cats | TaskCategory.objects.filter(pk=current.task_category_id)
        self.fields["work_unit"].queryset = units.distinct()
        self.fields["task_category"].queryset = cats.distinct()
        self.fields["supervisor"].queryset = get_user_model().objects.filter(
            is_active=True, role__in=["supervisor", "admin"]
        )

    def clean(self):
        cleaned = super().clean()
        start, end, day = cleaned.get("start_time"), cleaned.get("end_time"), cleaned.get("date")
        if start and end:
            if end <= start:
                self.add_error(
                    "end_time", "End time must be after the start time. Check AM and PM."
                )
            else:
                self.instance.hours = duration_hours(start, end)
        if day and day > timezone.localdate():
            self.add_error("date", "Time can only be logged for today or earlier.")
        if day and start and end and end > start:
            others = TimeEntry.objects.filter(
                intern=self.intern, date=day, start_time__isnull=False, end_time__isnull=False
            ).exclude(pk=self.instance.pk)
            for other in others:
                if overlaps(start, end, other.start_time, other.end_time):
                    raise forms.ValidationError(
                        f"This overlaps another entry on {day:%B %-d}, "
                        f"{other.start_time:%-I:%M %p} to {other.end_time:%-I:%M %p} "
                        f"({other.description or 'no description'}). Change the times or "
                        "edit that entry."
                    )
        return cleaned


class DateRangeForm(forms.Form):
    period = forms.ChoiceField(required=False, label="Period")
    start = forms.DateField(
        required=False, label="From", widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        required=False, label="To", widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, today=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.today = today or timezone.localdate()
        self.presets = presets(self.today)
        self.active_key = None
        self.fields["period"].choices = [("", "Custom range")] + [
            (p.key, p.label) for p in self.presets
        ]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and start > end:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return cleaned

    def get_range(self, default_key="quarter"):
        """Return (start, end, label) and set `active_key`. A preset wins over custom dates.

        `default_key="quarter"` means the current fiscal quarter.
        """
        data = self.cleaned_data if self.is_valid() else {}
        custom = bool(data.get("start") or data.get("end"))
        key = data.get("period") or ("" if custom else default_key)
        if key == "quarter":
            key = current_quarter_key(self.today)
        for p in self.presets:
            if p.key == key:
                self.active_key = p.key
                return p.start, p.end, p.label
        self.active_key = "custom"
        start, end = data.get("start"), data.get("end")
        first = f"{start:%b %-d, %Y}" if start else "the beginning"
        last = f"{end:%b %-d, %Y}" if end else "today"
        return start, end, f"{first} to {last}"

    @property
    def quarters(self):
        return [p for p in self.presets if p.kind == "quarter"]

    @property
    def shortcuts(self):
        return [p for p in self.presets if p.kind != "quarter"]
