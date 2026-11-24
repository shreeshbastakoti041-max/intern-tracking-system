from datetime import date, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from tracking.models import TimeEntry


def login(client, user):
    client.force_login(user)


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    for name in ["my_log", "dashboard", "records", "reports"]:
        resp = client.get(reverse(name))
        assert resp.status_code == 302 and reverse("login") in resp["Location"]


def test_visible_to_scopes_interns(intern_a, intern_b, supervisor, make_entry):
    mine = make_entry(intern_a)
    make_entry(intern_b)
    assert list(TimeEntry.objects.visible_to(intern_a.user)) == [mine]
    assert TimeEntry.objects.visible_to(supervisor).count() == 2


def test_intern_cannot_touch_other_interns_entries(client, intern_a, intern_b, make_entry):
    theirs = make_entry(intern_b)
    login(client, intern_a.user)
    assert client.get(reverse("entry_edit", args=[theirs.pk])).status_code == 404
    assert client.post(reverse("entry_delete", args=[theirs.pk])).status_code == 404
    assert TimeEntry.objects.filter(pk=theirs.pk).exists()


def test_intern_blocked_from_supervisor_pages(client, intern_a):
    login(client, intern_a.user)
    for name in ["dashboard", "records", "reports", "review_queue"]:
        assert client.get(reverse(name)).status_code == 403


def test_supervisor_is_read_only(client, supervisor, intern_a, make_entry):
    entry = make_entry(intern_a)
    login(client, supervisor)
    assert client.get(reverse("dashboard")).status_code == 200
    assert client.get(reverse("records")).status_code == 200
    assert client.get(reverse("intern_detail", args=[intern_a.pk])).status_code == 200
    assert client.get(reverse("entry_edit", args=[entry.pk])).status_code == 403
    assert client.get(reverse("review_queue")).status_code == 403


def _post_entry(client, **overrides):
    today = timezone.localdate()
    data = {
        "date": today.isoformat(), "start_time": "09:00", "end_time": "10:30",
        "work_unit": overrides.pop("work_unit"), "description": "Scanning",
        "is_backlog": "on",
    }
    data.update(overrides)
    return client.post(reverse("my_log"), data)


def test_intern_logs_entry_and_hours_are_computed(client, intern_a, lookups):
    login(client, intern_a.user)
    resp = _post_entry(client, work_unit=lookups["units"]["Finance"].pk)
    assert resp.status_code == 302
    entry = TimeEntry.objects.get()
    assert entry.intern == intern_a and entry.hours == 1.5 and entry.is_backlog
    assert entry.source == TimeEntry.Source.APP and entry.created_by == intern_a.user
    assert entry.history.count() == 1


def test_form_rejects_end_before_start_and_overlap(client, intern_a, lookups, make_entry):
    login(client, intern_a.user)
    unit = lookups["units"]["Finance"].pk
    resp = _post_entry(client, work_unit=unit, start_time="13:00", end_time="01:00")
    assert "End time must be after the start time" in resp.content.decode()
    make_entry(intern_a, day=timezone.localdate(), start=time(9, 30), end=time(11))
    resp = _post_entry(client, work_unit=unit)
    assert "overlaps another entry" in resp.content.decode()
    assert TimeEntry.objects.count() == 1


def test_form_rejects_future_date(client, intern_a, lookups):
    login(client, intern_a.user)
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    resp = _post_entry(client, work_unit=lookups["units"]["Finance"].pk, date=tomorrow)
    assert "today or earlier" in resp.content.decode()


def test_intern_edits_own_entry(client, intern_a, make_entry, lookups):
    entry = make_entry(intern_a)
    login(client, intern_a.user)
    resp = client.post(reverse("entry_edit", args=[entry.pk]), {
        "date": "2026-01-05", "start_time": "09:00", "end_time": "12:00",
        "work_unit": lookups["units"]["Admin"].pk, "description": "Updated",
    })
    assert resp.status_code == 302
    entry.refresh_from_db()
    assert entry.hours == 3 and entry.description == "Updated"
    assert entry.history.count() == 2


def test_unsafe_next_is_ignored(client, intern_a, make_entry):
    entry = make_entry(intern_a)
    login(client, intern_a.user)
    resp = client.post(reverse("entry_delete", args=[entry.pk]), {"next": "https://evil.example"})
    assert resp.status_code == 302 and "evil" not in resp["Location"]


def test_admin_review_queue(client, admin_user, intern_a, make_entry):
    flagged = make_entry(intern_a, review_flags=["hours_mismatch"], source="import")
    make_entry(intern_a, day=date(2026, 1, 6))
    login(client, admin_user)
    resp = client.get(reverse("review_queue"))
    assert resp.status_code == 200 and "match start/end" in resp.content.decode()
    client.post(reverse("mark_reviewed", args=[flagged.pk]))
    flagged.refresh_from_db()
    assert flagged.reviewed_by == admin_user and not flagged.needs_review


def test_records_filter_and_csv(client, supervisor, intern_a, intern_b, make_entry):
    make_entry(intern_a, description="=HYPERLINK(evil)")
    make_entry(intern_b, day=date(2026, 3, 1), description="Later")
    login(client, supervisor)
    resp = client.get(reverse("records"), {"start": "2026-02-01"})
    assert "Later" in resp.content.decode() and "HYPERLINK" not in resp.content.decode()
    resp = client.get(reverse("records"), {"export": "csv"})
    body = b"".join(resp.streaming_content).decode()
    assert body.count("\n") == 3  # header + 2 rows
    assert "'=HYPERLINK" in body  # formula injection neutralized


def test_role_flags_follow_role(make_user):
    admin = make_user("x@example.com", "admin")
    assert admin.is_staff and admin.is_superuser
    admin.role = "supervisor"
    admin.save()
    assert not admin.is_staff and not admin.is_superuser


def test_records_sorting(client, supervisor, intern_a, intern_b, make_entry):
    make_entry(intern_a, start=time(9), end=time(12))          # 3 h
    make_entry(intern_b, start=time(9), end=time(10))          # 1 h
    make_entry(intern_b, day=date(2026, 2, 1), start=time(9), end=time(11))  # 2 h
    login(client, supervisor)

    def hours(params):
        page = client.get(reverse("records"), params).context["page"]
        return [float(e.hours) for e in page]

    assert hours({"sort": "hours"}) == [1, 2, 3]
    assert hours({"sort": "-hours"}) == [3, 2, 1]
    assert hours({"sort": "-date"})[0] == 2  # newest first is the default too
    assert hours({"sort": "nonsense"}) == hours({})  # unknown keys fall back safely
    resp = client.get(reverse("records"), {"sort": "hours", "intern": intern_b.pk})
    assert [float(e.hours) for e in resp.context["page"]] == [1, 2]
    assert 'aria-sort="ascending"' in resp.content.decode()
