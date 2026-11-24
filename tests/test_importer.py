from datetime import date, time
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from imports.models import ImportBatch, ImportedRow
from imports.services import ImportRefused, run_import
from imports.workbook import parse_workbook, to_time
from tracking.models import InternProfile, TimeEntry, WorkUnit

from .workbook_factory import EXPECTED, build


@pytest.fixture
def workbook(tmp_path):
    return build(tmp_path / "synthetic.xlsx")


def test_to_time_variants():
    assert to_time("1:00PM") == (time(13), True)
    assert to_time(" 12:30 pm ") == (time(12, 30), True)
    assert to_time(0.375) == (time(9), False)
    assert to_time(None) == (None, False)
    with pytest.raises(ValueError):
        to_time("lunch")


def test_parse_finds_real_rows_and_skips_placeholders(workbook):
    parsed = parse_workbook(workbook)
    for sheet, exp in EXPECTED.items():
        rows = parsed.rows[sheet]
        assert len(rows) == exp["rows"]
        assert sum(r.hours for r in rows) == Decimal(exp["hours"])
    assert "Template - Intern" not in parsed.rows
    template = next(s for s in parsed.sheets if s.name == "Template - Intern")
    assert template.state == "hidden" and template.real_rows == 0


def test_parse_flags_problems_without_changing_values(workbook):
    parsed = parse_workbook(workbook)
    robin = parsed.rows["Robin - Finance"]
    assert robin[1].is_backlog is True and "invalid_yes_no" not in robin[1].flags  # "Y "
    assert robin[3].date is None and "missing_date" in robin[3].flags

    casey = parsed.rows["Casey - Data"]
    assert "text_time" in casey[0].flags and casey[0].start == time(13)
    assert casey[0].hours == Decimal("2")  # typed value kept
    ampm = casey[1]
    assert ampm.hours == Decimal("1.5")  # kept exactly as Excel had it
    assert {"hours_mismatch", "suspicious_duration"} <= set(ampm.flags)
    assert any("Coodinator" in w for w in parsed.warnings)
    assert "nonstandard_work_unit" in casey[2].flags
    # raw cells preserved, including formulas
    assert casey[1].raw["C"]["value"] == "Coodinator"
    assert robin[0].raw["H"]["formula"].startswith("=IF(")


def test_import_creates_everything_and_reconciles(workbook, admin_user):
    parsed = parse_workbook(workbook)
    result = run_import(parsed, user=admin_user)
    assert result.ok and result.entries == 7
    assert TimeEntry.objects.count() == 7 and ImportedRow.objects.count() == 7
    assert result.total_hours == Decimal("10.5")

    robin = InternProfile.objects.get(legacy_sheet_name="Robin - Finance")
    casey = InternProfile.objects.get(legacy_sheet_name="Casey - Data")
    assert robin.status == "active" and casey.status == "former"
    assert not InternProfile.objects.filter(display_name="").exists()

    legacy_unit = WorkUnit.objects.get(name="Scanning Project")
    assert legacy_unit.is_active is False
    assert TimeEntry.objects.filter(work_unit=legacy_unit).count() == 1

    rec = {r.sheet: r for r in result.per_intern}
    assert "Other" in rec["Robin - Finance"].explanation  # old Summary skipped "Other"
    assert TimeEntry.objects.filter(source="import").needing_review().count() == 4

    entry = TimeEntry.objects.get(description="Closeouts")
    assert entry.imported_row.row_number == 6 and entry.notes == "note here"
    assert entry.date == date(2026, 1, 5) and entry.hours == Decimal("2.5")


def test_dry_run_saves_nothing(workbook, db):
    result = run_import(parse_workbook(workbook), dry_run=True)
    assert result.ok and result.entries == 7 and result.batch_id is None
    assert TimeEntry.objects.count() == 0 and ImportBatch.objects.count() == 0


def test_reimport_rules(workbook, intern_a, make_entry):
    app_entry = make_entry(intern_a)  # typed into the app: must survive --replace
    parsed = parse_workbook(workbook)
    run_import(parsed)
    with pytest.raises(ImportRefused, match="already been imported"):
        run_import(parsed)
    with pytest.raises(ImportRefused, match="--replace"):
        run_import(parsed, force=True)
    result = run_import(parsed, force=True, replace=True)
    assert result.replaced_entries == 7
    assert TimeEntry.objects.filter(source="import").count() == 7
    assert TimeEntry.objects.filter(pk=app_entry.pk).exists()


def test_management_command(workbook, capsys, db):
    call_command("import_workbook", str(workbook), "--dry-run")
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "Reconciliation" in out and "MISMATCH" not in out
    with pytest.raises(CommandError):
        call_command("import_workbook", "/nope/missing.xlsx")
