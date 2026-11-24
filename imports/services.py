"""Load a ParsedWorkbook into the database and reconcile the totals."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from tracking.models import Department, InternProfile, TaskCategory, TimeEntry, WorkUnit

from .models import ImportBatch, ImportedRow
from .workbook import ParsedWorkbook, norm

TOLERANCE = Decimal("0.01")
STATUS_MAP = {norm(label): value for value, label in InternProfile.Status.choices}


class ImportRefused(Exception):
    """The import was not saved. `result` holds the reconciliation when one was computed."""

    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


class _DryRun(Exception):
    pass


@dataclass
class InternReconciliation:
    intern: str
    sheet: str
    excel_rows: int
    imported_rows: int
    excel_hours: Decimal
    db_hours: Decimal
    old_summary_hours: float | None
    flagged: int
    explanation: str = ""

    @property
    def ok(self) -> bool:
        return (
            self.excel_rows == self.imported_rows
            and abs(self.excel_hours - self.db_hours) <= TOLERANCE
        )


@dataclass
class ImportResult:
    batch_id: int | None
    dry_run: bool
    entries: int = 0
    flagged: int = 0
    total_hours: Decimal = Decimal("0")
    replaced_entries: int = 0
    edited_since_import: int = 0
    per_intern: list[InternReconciliation] = field(default_factory=list)
    flag_counts: dict[str, int] = field(default_factory=dict)
    created_lookups: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.per_intern)


def _lookup(model, name: str, created: dict, *, active=True, sort_order=0):
    obj = model.objects.filter(name__iexact=name).first()
    if obj:
        return obj
    obj = model.objects.create(name=name, is_active=active, sort_order=sort_order)
    created.setdefault(model._meta.verbose_name_plural.title(), []).append(name)
    return obj


def _seed_lists(parsed: ParsedWorkbook, created: dict) -> None:
    for model, title in (
        (Department, "Home Departments"),
        (WorkUnit, "Work Units"),
        (TaskCategory, "Task Categories"),
    ):
        for i, name in enumerate(parsed.lists.get(title, []), start=1):
            _lookup(model, name, created, sort_order=i * 10)


def _explain_summary_gap(rows, summary_units: list[str], excel_hours, old) -> str:
    if old is None:
        return "intern not in old Summary"
    if abs(Decimal(str(old)) - excel_hours) <= TOLERANCE:
        return ""
    counted = {norm(u) for u in summary_units}
    missing: dict[str, Decimal] = {}
    for r in rows:
        if norm(r.work_unit) not in counted:
            missing[r.work_unit or "(blank)"] = missing.get(r.work_unit or "(blank)", 0) + r.hours
    if missing:
        parts = ", ".join(f"{k} {v:.2f} h" for k, v in sorted(missing.items()))
        return f"old Summary ignored work units: {parts}"
    return "old Summary value differs (stale cached value?)"


def run_import(
    parsed: ParsedWorkbook, *, user=None, dry_run=False, replace=False, force=False
) -> ImportResult:
    """Import everything in one transaction. Dry runs do all the work, then roll back."""
    result = ImportResult(batch_id=None, dry_run=dry_run, warnings=list(parsed.warnings))

    previous = ImportBatch.objects.all()
    if previous.filter(sha256=parsed.sha256).exists() and not force:
        raise ImportRefused(
            "This exact file has already been imported. Use --force to import it again "
            "(together with --replace to avoid duplicates)."
        )
    prior_entries = TimeEntry.objects.filter(source=TimeEntry.Source.IMPORT)
    if prior_entries.exists() and not replace:
        raise ImportRefused(
            f"{prior_entries.count()} previously imported entries exist. Re-run with --replace "
            "to delete them and import this file instead (entries typed into the app are kept)."
        )

    try:
        with transaction.atomic():
            if replace:
                result.edited_since_import = sum(
                    1 for e in prior_entries.only("id") if e.history.count() > 1
                )
                result.replaced_entries = prior_entries.count()
                ImportedRow.objects.filter(entry__in=prior_entries).delete()
                prior_entries.delete()

            created: dict[str, list[str]] = {}
            _seed_lists(parsed, created)

            batch = ImportBatch.objects.create(
                filename=parsed.filename, sha256=parsed.sha256, imported_by=user
            )
            profiles: dict[str, InternProfile] = {}
            for pi in parsed.interns:
                if not pi.sheet_name:
                    continue
                profile = InternProfile.objects.filter(legacy_sheet_name=pi.sheet_name).first()
                if profile is None:
                    status = STATUS_MAP.get(norm(pi.status))
                    if status is None:
                        result.warnings.append(
                            f"{pi.name}: unknown status '{pi.status}', set to Active."
                        )
                        status = InternProfile.Status.ACTIVE
                    profile = InternProfile.objects.create(
                        display_name=pi.name,
                        legacy_sheet_name=pi.sheet_name,
                        home_department=(
                            _lookup(Department, pi.home_dept, created) if pi.home_dept else None
                        ),
                        status=status,
                        start_date=pi.start_date,
                        end_date=pi.end_date,
                        notes=pi.notes,
                        include_in_summary=pi.include_in_summary,
                        sort_order=pi.sort_order,
                    )
                profiles[pi.sheet_name] = profile

            unit_cache: dict[str, WorkUnit] = {}
            cat_cache: dict[str, TaskCategory] = {}
            for sheet, rows in parsed.rows.items():
                profile = profiles[sheet]
                for row in rows:
                    unit = None
                    if row.work_unit:
                        key = norm(row.work_unit)
                        if key not in unit_cache:
                            unit_cache[key] = _lookup(
                                WorkUnit, row.work_unit, created, active=False, sort_order=1000
                            )
                        unit = unit_cache[key]
                    category = None
                    if row.task_category:
                        key = norm(row.task_category)
                        if key not in cat_cache:
                            cat_cache[key] = _lookup(
                                TaskCategory, row.task_category, created, active=False,
                                sort_order=1000,
                            )
                        category = cat_cache[key]
                    entry = TimeEntry.objects.create(
                        intern=profile,
                        date=row.date,
                        work_unit=unit,
                        task_category=category,
                        description=row.description[:500],
                        is_backlog=row.is_backlog,
                        ai_used=row.ai_used,
                        start_time=row.start,
                        end_time=row.end,
                        hours=row.hours,
                        supervisor_text=row.supervisor[:150],
                        notes=row.notes,
                        source=TimeEntry.Source.IMPORT,
                        review_flags=row.flags,
                        created_by=user,
                    )
                    ImportedRow.objects.create(
                        batch=batch,
                        sheet_name=sheet,
                        row_number=row.row_number,
                        raw=row.raw,
                        entry=entry,
                    )
                    result.entries += 1
                    if row.flags:
                        result.flagged += 1
                    for f in row.flags:
                        result.flag_counts[f] = result.flag_counts.get(f, 0) + 1

                excel_hours = sum((r.hours for r in rows), Decimal("0"))
                db_hours = TimeEntry.objects.filter(
                    intern=profile, imported_row__batch=batch
                ).aggregate(h=Sum("hours"))["h"] or Decimal("0")
                old = parsed.summary_hours.get(sheet)
                result.per_intern.append(
                    InternReconciliation(
                        intern=profile.display_name,
                        sheet=sheet,
                        excel_rows=len(rows),
                        imported_rows=ImportedRow.objects.filter(
                            batch=batch, sheet_name=sheet
                        ).count(),
                        excel_hours=excel_hours,
                        db_hours=db_hours,
                        old_summary_hours=old,
                        flagged=sum(1 for r in rows if r.flags),
                        explanation=_explain_summary_gap(
                            rows, parsed.summary_units, excel_hours, old
                        ),
                    )
                )

            result.total_hours = sum((r.db_hours for r in result.per_intern), Decimal("0"))
            result.created_lookups = created
            batch.entry_count = result.entries
            batch.flagged_count = result.flagged
            batch.total_hours = result.total_hours
            batch.reconciliation = {
                "per_intern": [
                    {
                        "intern": r.intern,
                        "sheet": r.sheet,
                        "excel_rows": r.excel_rows,
                        "imported_rows": r.imported_rows,
                        "excel_hours": str(r.excel_hours),
                        "db_hours": str(r.db_hours),
                        "old_summary_hours": r.old_summary_hours,
                        "flagged": r.flagged,
                        "explanation": r.explanation,
                    }
                    for r in result.per_intern
                ],
                "flag_counts": result.flag_counts,
                "sheets": [s.__dict__ for s in parsed.sheets],
                "warnings": result.warnings,
            }
            batch.save()
            result.batch_id = batch.pk

            if not result.ok:
                raise ImportRefused("Reconciliation failed; nothing was saved.", result)
            if dry_run:
                raise _DryRun
    except _DryRun:
        result.batch_id = None
    return result
