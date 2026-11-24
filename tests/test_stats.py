from datetime import date, time
from decimal import Decimal

from tracking.models import TimeEntry, WorkUnit
from tracking.services import stats


def test_summary_counts_every_unit(intern_a, make_entry):
    make_entry(intern_a, unit="Finance", is_backlog=True)
    make_entry(intern_a, start=time(10), end=time(12), unit="Other", ai_used=True)
    legacy = WorkUnit.objects.create(name="Scanning Project", is_active=False, sort_order=1000)
    TimeEntry.objects.create(intern=intern_a, date=date(2026, 1, 6), work_unit=legacy,
                             hours=Decimal("0.5"))
    TimeEntry.objects.create(intern=intern_a, date=date(2026, 1, 7), hours=Decimal("0.25"))

    kpis = stats.summarize(TimeEntry.objects.all())
    assert kpis["total_hours"] == Decimal("3.75")
    assert kpis["backlog_hours"] == Decimal("1")
    assert kpis["ai_hours"] == Decimal("2")
    assert kpis["task_count"] == 4
    assert kpis["ai_task_count"] == 1

    matrix = stats.intern_unit_matrix(TimeEntry.objects.all())
    assert matrix.units == ["Finance", "Other", "Scanning Project", stats.NO_UNIT]
    assert matrix.grand_total == Decimal("3.75")
    assert sum(matrix.unit_totals) == matrix.grand_total


def test_matrix_rows_per_intern(intern_a, intern_b, make_entry):
    make_entry(intern_a, unit="Finance")
    make_entry(intern_b, unit="Pre-Award", start=time(8), end=time(11))
    matrix = stats.intern_unit_matrix(TimeEntry.objects.order_by("-date"))
    assert [r.intern for r in matrix.rows] == ["Alpha", "Bravo"]
    assert [r.total for r in matrix.rows] == [Decimal("1"), Decimal("3")]


def test_empty_summary_is_zero(db):
    kpis = stats.summarize(TimeEntry.objects.none())
    assert kpis["total_hours"] == 0
    assert kpis["task_count"] == 0
