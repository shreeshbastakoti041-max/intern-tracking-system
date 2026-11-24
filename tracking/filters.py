import django_filters
from django import forms
from django.db.models import Q

from .models import Department, InternProfile, TimeEntry, WorkUnit

YES_NO = forms.Select(choices=[("", "Any"), ("true", "Yes"), ("false", "No")])


class TimeEntryFilter(django_filters.FilterSet):
    start = django_filters.DateFilter(
        field_name="date", lookup_expr="gte", label="From",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end = django_filters.DateFilter(
        field_name="date", lookup_expr="lte", label="To",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    intern = django_filters.ModelChoiceFilter(queryset=InternProfile.objects.all())
    department = django_filters.ModelChoiceFilter(
        field_name="intern__home_department", queryset=Department.objects.all(),
        label="Home department",
    )
    work_unit = django_filters.ModelChoiceFilter(queryset=WorkUnit.objects.all())
    status = django_filters.ChoiceFilter(
        field_name="intern__status", choices=InternProfile.Status.choices, label="Status"
    )
    is_backlog = django_filters.BooleanFilter(label="Backlog", widget=YES_NO)
    ai_used = django_filters.BooleanFilter(label="AI used", widget=YES_NO)
    needs_review = django_filters.BooleanFilter(
        label="Needs a check", method="filter_needs_review", widget=YES_NO
    )
    q = django_filters.CharFilter(label="Search tasks and notes", method="filter_search")

    class Meta:
        model = TimeEntry
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(description__icontains=value)
            | Q(notes__icontains=value)
            | Q(supervisor_text__icontains=value)
        )

    def filter_needs_review(self, queryset, name, value):
        flagged = Q(reviewed_at__isnull=True) & ~Q(review_flags=[])
        return queryset.filter(flagged) if value else queryset.exclude(flagged)
