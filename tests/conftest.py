from datetime import date, time

import pytest

from tracking.models import Department, InternProfile, TimeEntry, WorkUnit


@pytest.fixture
def lookups(db):
    depts = {n: Department.objects.create(name=n, sort_order=i) for i, n in
             enumerate(["Pre-Award", "Finance", "Systems & Data"])}
    units = {n: WorkUnit.objects.create(name=n, sort_order=i) for i, n in
             enumerate(["Admin", "Pre-Award", "Finance", "Systems & Data", "Training", "Other"])}
    return {"depts": depts, "units": units}


@pytest.fixture
def make_user(db, django_user_model):
    def make(email, role="intern", **extra):
        return django_user_model.objects.create_user(
            email=email, password="test-pass-123!", role=role, **extra
        )
    return make


@pytest.fixture
def admin_user(make_user):
    return make_user("admin@example.com", "admin")


@pytest.fixture
def supervisor(make_user):
    return make_user("boss@example.com", "supervisor", first_name="Pat")


@pytest.fixture
def intern_a(make_user, lookups):
    user = make_user("a@example.com", "intern")
    return InternProfile.objects.create(
        user=user, display_name="Alpha", home_department=lookups["depts"]["Finance"], sort_order=1
    )


@pytest.fixture
def intern_b(make_user, lookups):
    user = make_user("b@example.com", "intern")
    return InternProfile.objects.create(
        user=user, display_name="Bravo", home_department=lookups["depts"]["Pre-Award"], sort_order=2
    )


@pytest.fixture
def make_entry(lookups):
    def make(intern, day=date(2026, 1, 5), start=time(9), end=time(10), unit="Finance", **kw):
        from tracking.services.hours import duration_hours

        kw.setdefault("description", "Task")
        return TimeEntry.objects.create(
            intern=intern, date=day, start_time=start, end_time=end,
            hours=kw.pop("hours", duration_hours(start, end)),
            work_unit=lookups["units"].get(unit) if unit else None, **kw,
        )
    return make
