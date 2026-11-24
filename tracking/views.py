from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.permissions import admin_required, supervisor_or_admin_required

from .filters import TimeEntryFilter
from .forms import DateRangeForm, TimeEntryForm
from .models import InternProfile, TimeEntry
from .services import stats
from .services.periods import week_range

COPY_FIELDS = ["work_unit", "task_category", "description", "is_backlog", "ai_used", "supervisor"]


def _intern_profile(user):
    return getattr(user, "intern_profile", None)


def _safe_next(request, fallback: str) -> str:
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def _paginate(request, qs, per_page=50):
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


def _entries(qs):
    return qs.select_related("intern", "work_unit", "task_category", "supervisor")


# Column sorting for paginated entry tables (whitelisted; "-" prefix = descending).
SORTS = {
    "date": ("date", "start_time"),
    "intern": ("intern__display_name", "date"),
    "unit": ("work_unit__name", "date"),
    "hours": ("hours", "date"),
}


def _sorted(request, qs, default="-date"):
    key = request.GET.get("sort") or default
    name = key.lstrip("-")
    if name not in SORTS:
        key, name = default, default.lstrip("-")
    prefix = "-" if key.startswith("-") else ""
    return qs.order_by(*[prefix + f for f in SORTS[name]], prefix + "id"), key


def _query_without(request, *names):
    query = request.GET.copy()
    for name in names:
        query.pop(name, None)
    return query.urlencode()


@login_required
def home(request):
    if request.user.can_view_all:
        return redirect("dashboard")
    return redirect("my_log")


# --------------------------------------------------------------------------- intern pages


@login_required
def my_log(request):
    profile = _intern_profile(request.user)
    if profile is None:
        return render(request, "tracking/no_profile.html", status=403)

    today = timezone.localdate()
    try:
        anchor = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        anchor = today
    week_start, week_end = week_range(anchor)

    if request.method == "POST":
        entry = TimeEntry(intern=profile, created_by=request.user, source=TimeEntry.Source.APP)
        form = TimeEntryForm(request.POST, instance=entry, intern=profile)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f"Saved {saved.hours:.2f} hours on {saved.date:%A, %B %-d}.")
            return redirect(f"{reverse('my_log')}?week={saved.date.isoformat()}")
    else:
        initial = {"date": today if week_start <= today <= week_end else week_start}
        copy_id = request.GET.get("copy")
        if copy_id and copy_id.isdigit():
            source = profile.entries.filter(pk=copy_id).first()
            if source:
                initial.update({f: getattr(source, f) for f in COPY_FIELDS})
        form = TimeEntryForm(initial=initial, intern=profile)

    week_entries = list(
        _entries(profile.entries.in_range(week_start, week_end)).order_by("date", "start_time")
    )
    days = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        items = [e for e in week_entries if e.date == day]
        days.append({"date": day, "entries": items, "total": sum(e.hours for e in items)})

    return render(
        request,
        "tracking/my_log.html",
        {
            "profile": profile,
            "form": form,
            "days": days,
            "week_start": week_start,
            "week_end": week_end,
            "week_total": sum(e.hours for e in week_entries),
            "prev_week": (week_start - timedelta(days=7)).isoformat(),
            "next_week": (week_start + timedelta(days=7)).isoformat(),
            "is_current_week": week_start <= today <= week_end,
        },
    )


@login_required
def entry_edit(request, pk):
    entry = get_object_or_404(TimeEntry.objects.visible_to(request.user), pk=pk)
    if not entry.can_edit(request.user):
        raise PermissionDenied
    fallback = (
        f"{reverse('my_log')}?week={entry.date.isoformat()}" if entry.date else reverse("home")
    )
    form = TimeEntryForm(request.POST or None, instance=entry, intern=entry.intern)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect(_safe_next(request, fallback))
    return render(
        request,
        "tracking/entry_form.html",
        {"form": form, "entry": entry, "next": _safe_next(request, fallback)},
    )


@login_required
def entry_delete(request, pk):
    entry = get_object_or_404(TimeEntry.objects.visible_to(request.user), pk=pk)
    if not entry.can_edit(request.user):
        raise PermissionDenied
    fallback = (
        f"{reverse('my_log')}?week={entry.date.isoformat()}" if entry.date else reverse("home")
    )
    if request.method == "POST":
        entry.delete()
        messages.success(request, "Entry deleted.")
        return redirect(_safe_next(request, fallback))
    return render(
        request,
        "tracking/entry_confirm_delete.html",
        {"entry": entry, "next": _safe_next(request, fallback)},
    )


@login_required
def my_summary(request):
    profile = _intern_profile(request.user)
    if profile is None:
        return render(request, "tracking/no_profile.html", status=403)
    range_form = DateRangeForm(request.GET or None)
    start, end, label = range_form.get_range(default_key="fy")
    qs = profile.entries.in_range(start, end)
    ordered, sort = _sorted(request, _entries(qs))
    return render(
        request,
        "tracking/my_summary.html",
        {
            "profile": profile,
            "range_form": range_form,
            "range_label": label,
            "start": start,
            "end": end,
            "kpis": stats.summarize(qs),
            "by_unit": stats.hours_by_unit(qs),
            "page": _paginate(request, ordered),
            "sort": sort,
            "querystring": _query_without(request, "page"),
            "sort_query": _query_without(request, "page", "sort"),
        },
    )


# --------------------------------------------------------------------------- supervisor pages


@supervisor_or_admin_required
def dashboard(request):
    range_form = DateRangeForm(request.GET or None)
    start, end, label = range_form.get_range(default_key="quarter")
    qs = (
        TimeEntry.objects.visible_to(request.user)
        .filter(intern__include_in_summary=True)
        .in_range(start, end)
    )
    interns = InternProfile.objects.select_related("home_department").annotate(
        last_entry=Max("entries__date"),
        flagged=Count(
            "entries",
            filter=Q(entries__reviewed_at__isnull=True) & ~Q(entries__review_flags=[]),
        ),
    )
    return render(
        request,
        "tracking/dashboard.html",
        {
            "range_form": range_form,
            "range_label": label,
            "start": start,
            "end": end,
            "kpis": stats.summarize(qs),
            "matrix": stats.intern_unit_matrix(qs),
            "interns": interns,
            "review_count": TimeEntry.objects.needing_review().count(),
        },
    )


@supervisor_or_admin_required
def records(request):
    base = _entries(TimeEntry.objects.visible_to(request.user))
    entry_filter = TimeEntryFilter(request.GET or None, queryset=base)
    qs, sort = _sorted(request, entry_filter.qs)
    if request.GET.get("export") == "csv":
        from reports.builders import entries_csv_response

        return entries_csv_response(qs, "records")
    return render(
        request,
        "tracking/records.html",
        {
            "filter": entry_filter,
            "kpis": stats.summarize(qs),
            "page": _paginate(request, qs),
            "sort": sort,
            "querystring": _query_without(request, "page", "export"),
            "sort_query": _query_without(request, "page", "export", "sort"),
        },
    )


@supervisor_or_admin_required
def intern_detail(request, pk):
    profile = get_object_or_404(
        InternProfile.objects.select_related("home_department", "user"), pk=pk
    )
    range_form = DateRangeForm(request.GET or None)
    start, end, label = range_form.get_range(default_key="all")
    qs = TimeEntry.objects.visible_to(request.user).filter(intern=profile).in_range(start, end)
    ordered, sort = _sorted(request, _entries(qs))
    return render(
        request,
        "tracking/intern_detail.html",
        {
            "profile": profile,
            "range_form": range_form,
            "range_label": label,
            "start": start,
            "end": end,
            "kpis": stats.summarize(qs),
            "by_unit": stats.hours_by_unit(qs),
            "page": _paginate(request, ordered),
            "sort": sort,
            "querystring": _query_without(request, "page"),
            "sort_query": _query_without(request, "page", "sort"),
        },
    )


# --------------------------------------------------------------------------- admin pages


@admin_required
def review_queue(request):
    qs = (
        _entries(TimeEntry.objects.needing_review())
        .select_related("imported_row")
        .order_by("intern__sort_order", "date", "start_time")
    )
    return render(request, "tracking/review_queue.html", {"page": _paginate(request, qs, 25)})


@admin_required
@require_POST
def mark_reviewed(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk)
    entry.reviewed_at = timezone.now()
    entry.reviewed_by = request.user
    entry.save(update_fields=["reviewed_at", "reviewed_by", "updated_at"])
    when = f"{entry.date:%B %-d}" if entry.date else "undated"
    messages.success(request, f"Marked {entry.intern}'s {when} entry as checked.")
    return redirect(_safe_next(request, reverse("review_queue")))
