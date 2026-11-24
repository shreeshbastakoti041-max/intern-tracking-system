"""Excel / CSV report builders. Totals always come from tracking.services.stats."""

from __future__ import annotations

import csv
from datetime import date
from io import BytesIO

from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from tracking.services import stats

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)
HOURS_FMT = "0.00"

ENTRY_COLUMNS = [
    ("Date", 12),
    ("Intern", 16),
    ("Home Department", 18),
    ("Work Unit", 18),
    ("Task Category", 16),
    ("Task Description", 48),
    ("Backlog", 9),
    ("AI Used", 9),
    ("Start", 9),
    ("End", 9),
    ("Hours", 9),
    ("Supervisor / Lead", 20),
    ("Notes", 36),
    ("Source", 10),
    ("Review Flags", 28),
]


def safe_text(value):
    """Neutralize spreadsheet formula injection (=, +, -, @ at the start of text)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _entry_values(e) -> list:
    return [
        e.date,
        e.intern.display_name,
        e.intern.home_department.name if e.intern.home_department_id else "",
        e.work_unit.name if e.work_unit_id else "",
        e.task_category.name if e.task_category_id else "",
        e.description,
        "Y" if e.is_backlog else "N",
        "Y" if e.ai_used else "N",
        e.start_time,
        e.end_time,
        e.hours,
        e.supervisor_display,
        e.notes,
        e.get_source_display(),
        ", ".join(e.review_flags) if e.needs_review else "",
    ]


def _prepare(qs):
    return qs.select_related(
        "intern", "intern__home_department", "work_unit", "task_category", "supervisor"
    ).order_by("date", "intern__sort_order", "intern__display_name", "start_time")


def period_text(start: date | None, end: date | None) -> str:
    if not start and not end:
        return "All dates"
    first = f"{start:%b %d, %Y}" if start else "Beginning"
    last = f"{end:%b %d, %Y}" if end else "Today"
    return first if start == end else f"{first} – {last}"


# --------------------------------------------------------------------------- xlsx helpers


def _header(ws, row: int, labels: list[str]) -> None:
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row, col, label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _title_block(ws, title: str, start, end, generated_by) -> int:
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Period: {period_text(start, end)}"
    ws["A3"] = f"Generated {timezone.localtime():%b %d, %Y %I:%M %p}" + (
        f" by {generated_by}" if generated_by else ""
    )
    return 5


def _kpi_block(ws, row: int, kpis: dict) -> int:
    items = [
        ("Total hours", kpis["total_hours"], HOURS_FMT),
        ("Backlog hours", kpis["backlog_hours"], HOURS_FMT),
        ("AI-assisted hours", kpis["ai_hours"], HOURS_FMT),
        ("Tasks", kpis["task_count"], "0"),
        ("Backlog tasks", kpis["backlog_task_count"], "0"),
        ("AI-assisted tasks", kpis["ai_task_count"], "0"),
    ]
    _header(ws, row, ["Measure", "Value"])
    for i, (label, value, fmt) in enumerate(items, start=1):
        ws.cell(row + i, 1, label)
        cell = ws.cell(row + i, 2, value)
        cell.number_format = fmt
    return row + len(items) + 2


def _entries_sheet(wb: Workbook, qs) -> None:
    ws = wb.create_sheet("Entries")
    _header(ws, 1, [c for c, _ in ENTRY_COLUMNS])
    for i, (_, width) in enumerate(ENTRY_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    r = 1
    for r, e in enumerate(_prepare(qs).iterator(chunk_size=500), start=2):
        for c, value in enumerate(_entry_values(e), start=1):
            cell = ws.cell(r, c, safe_text(value))
            if c == 1 and value:
                cell.number_format = "yyyy-mm-dd"
            elif c in (9, 10) and value:
                cell.number_format = "h:mm AM/PM"
            elif c == 11:
                cell.number_format = HOURS_FMT
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(ENTRY_COLUMNS))}{max(r, 1)}"


def _to_response(wb: Workbook, filename: str) -> HttpResponse:
    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=XLSX_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _filename(stem: str, start, end, ext: str) -> str:
    span = f"{start or 'start'}_to_{end or timezone.localdate()}"
    return f"{slugify(stem)}_{span}.{ext}"


# --------------------------------------------------------------------------- public builders


def intern_workbook(profile, qs, start, end, generated_by=None) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    row = _title_block(ws, f"Intern report: {profile.display_name}", start, end, generated_by)
    ws.cell(row, 1, "Home department").font = BOLD
    ws.cell(row, 2, profile.home_department.name if profile.home_department_id else "")
    ws.cell(row + 1, 1, "Status").font = BOLD
    ws.cell(row + 1, 2, profile.get_status_display())
    row = _kpi_block(ws, row + 3, stats.summarize(qs))

    _header(ws, row, ["Work unit", "Hours", "Tasks"])
    by_unit = stats.hours_by_unit(qs)
    for i, item in enumerate(by_unit, start=1):
        ws.cell(row + i, 1, item["unit"])
        ws.cell(row + i, 2, item["hours"]).number_format = HOURS_FMT
        ws.cell(row + i, 3, item["tasks"])
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 10
    _entries_sheet(wb, qs)
    return wb


def all_interns_workbook(qs, start, end, generated_by=None) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    row = _title_block(ws, "OSP intern summary report", start, end, generated_by)
    row = _kpi_block(ws, row, stats.summarize(qs))

    matrix = stats.intern_unit_matrix(qs)
    ws.cell(row, 1, "Hours by intern and work unit").font = BOLD
    row += 1
    labels = ["Intern", *matrix.units, "Total hours", "Tasks", "Backlog hours", "AI hours",
              "AI tasks"]
    _header(ws, row, labels)
    for i, mrow in enumerate(matrix.rows, start=1):
        values = [mrow.intern, *mrow.cells, mrow.total, mrow.tasks, mrow.backlog_hours,
                  mrow.ai_hours, mrow.ai_tasks]
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row + i, c, safe_text(value))
            if 1 < c <= len(matrix.units) + 2 or c in (len(labels) - 2, len(labels) - 1):
                cell.number_format = HOURS_FMT
    total_row = row + len(matrix.rows) + 1
    ws.cell(total_row, 1, "Total").font = BOLD
    for c, value in enumerate([*matrix.unit_totals, matrix.grand_total], start=2):
        cell = ws.cell(total_row, c, value)
        cell.number_format = HOURS_FMT
        cell.font = BOLD
    ws.column_dimensions["A"].width = 22
    for c in range(2, len(labels) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14
    _entries_sheet(wb, qs)
    return wb


def intern_report_response(profile, qs, start, end, generated_by=None) -> HttpResponse:
    wb = intern_workbook(profile, qs, start, end, generated_by)
    return _to_response(wb, _filename(f"{profile.display_name}-report", start, end, "xlsx"))


def all_interns_report_response(qs, start, end, generated_by=None) -> HttpResponse:
    wb = all_interns_workbook(qs, start, end, generated_by)
    return _to_response(wb, _filename("all-interns-report", start, end, "xlsx"))


class _Echo:
    def write(self, value):
        return value


def entries_csv_response(qs, stem: str, start=None, end=None) -> StreamingHttpResponse:
    writer = csv.writer(_Echo())

    def rows():
        yield writer.writerow([c for c, _ in ENTRY_COLUMNS])
        for e in _prepare(qs).iterator(chunk_size=500):
            values = _entry_values(e)
            values[8] = e.start_time.strftime("%H:%M") if e.start_time else ""
            values[9] = e.end_time.strftime("%H:%M") if e.end_time else ""
            values[10] = f"{e.hours:.2f}"
            yield writer.writerow([safe_text(v) if v is not None else "" for v in values])

    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename(stem, start, end, "csv")}"'
    return response
