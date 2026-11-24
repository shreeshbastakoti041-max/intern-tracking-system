"""Read the legacy OSP Intern Tracker workbook into plain Python objects.

This module never touches the database, so it can be tested in isolation.
The rule throughout is *preserve, then flag*: every cell is kept verbatim in
`ParsedRow.raw`, and anything questionable is reported in `ParsedRow.flags`
instead of being silently changed.
"""

from __future__ import annotations

import hashlib
import re
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import from_excel

from tracking.services.hours import duration_hours, to_hours

DIRECTORY_SHEET = "Intern Directory"
LISTS_SHEET = "Lists"
SUMMARY_SHEET = "Summary"

# Log-tab header text -> field name. Unknown headers are still kept in `raw`.
LOG_HEADERS = {
    "date": "date",
    "intern name": "intern_name",
    "home department": "home_dept",
    "work unit": "work_unit",
    "task category": "task_category",
    "task/backlog description": "description",
    "backlog y/n": "backlog",
    "ai use y/n": "ai",
    "duration (hrs)": "hours",
    "start time": "start",
    "end time": "end",
    "supervisor/lead": "supervisor",
    "notes": "notes",
}

MISMATCH_TOLERANCE = Decimal("0.02")  # hours (~1 minute)
SUSPICIOUS_HOURS = Decimal("12")

TEXT_TIME_FORMATS = ["%I:%M%p", "%I%p", "%I:%M:%S%p", "%H:%M", "%H:%M:%S"]
TEXT_DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"]


# --------------------------------------------------------------------------- data classes


@dataclass
class ParsedIntern:
    name: str
    sheet_name: str
    home_dept: str
    status: str
    start_date: date | None
    end_date: date | None
    notes: str
    include_in_summary: bool
    sort_order: int
    row_number: int
    raw: dict


@dataclass
class ParsedRow:
    sheet_name: str
    row_number: int
    raw: dict
    date: date | None = None
    intern_name: str = ""
    home_dept: str = ""
    work_unit: str = ""
    task_category: str = ""
    description: str = ""
    is_backlog: bool = False
    ai_used: bool = False
    hours: Decimal = Decimal("0")
    start: time | None = None
    end: time | None = None
    supervisor: str = ""
    notes: str = ""
    flags: list[str] = field(default_factory=list)

    def flag(self, code: str) -> None:
        if code not in self.flags:
            self.flags.append(code)


@dataclass
class SheetReport:
    name: str
    state: str
    kind: str  # "intern_log" | "directory" | "lists" | "summary" | "other"
    real_rows: int = 0
    note: str = ""


@dataclass
class ParsedWorkbook:
    filename: str
    sha256: str
    lists: dict[str, list[str]]
    interns: list[ParsedIntern]
    rows: dict[str, list[ParsedRow]]  # sheet name -> rows
    sheets: list[SheetReport]
    summary_hours: dict[str, float]  # sheet name -> "Total Hours" cached in Summary
    summary_units: list[str]  # work units the old Summary had columns for
    warnings: list[str] = field(default_factory=list)

    @property
    def all_rows(self) -> list[ParsedRow]:
        return [r for rows in self.rows.values() for r in rows]


# --------------------------------------------------------------------------- value helpers


def clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def jsonable(value):
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    return str(value)


def to_date(value) -> date | None:
    """Excel date cell -> date. Raises ValueError for unreadable values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        return from_excel(value).date()
    text = str(value).strip()
    for fmt in TEXT_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unreadable date: {value!r}")


def _safe_date(value) -> date | None:
    try:
        return to_date(value)
    except ValueError:
        return None


def _time_from_fraction(fraction: float) -> time:
    seconds = round((fraction % 1) * 86400) % 86400
    return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)


def to_time(value) -> tuple[time | None, bool]:
    """Excel time cell -> (time, was_text). Raises ValueError for unreadable values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, False
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0), False
    if isinstance(value, time):
        return value.replace(microsecond=0), False
    if isinstance(value, timedelta):
        return _time_from_fraction(value.total_seconds() / 86400), False
    if isinstance(value, int | float):
        return _time_from_fraction(float(value)), False
    text = re.sub(r"\s+", "", str(value)).upper().replace(".", "")
    for fmt in TEXT_TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time(), True
        except ValueError:
            continue
    raise ValueError(f"unreadable time: {value!r}")


def to_number(value) -> Decimal | None:
    """Duration cell -> hours, keeping the workbook's underlying numeric value."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("boolean hours")
    if isinstance(value, int | float):
        return to_hours(value)
    if isinstance(value, time):  # a time typed into the hours column: Excel stores a day fraction
        return to_hours((value.hour * 3600 + value.minute * 60 + value.second) / 86400)
    if isinstance(value, timedelta):
        return to_hours(value.total_seconds() / 86400)
    try:
        return to_hours(Decimal(str(value).strip()))
    except InvalidOperation as exc:
        raise ValueError(f"unreadable hours: {value!r}") from exc


def yes_no(value, row: ParsedRow) -> bool:
    """Mirror the old Summary's `"Y*"` test; flag anything that isn't plainly Y/N."""
    text = clean_text(value).upper()
    if not text:
        return False
    if text not in {"Y", "N", "YES", "NO"}:
        row.flag("invalid_yes_no")
    return text.startswith("Y")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


# --------------------------------------------------------------------------- sheet readers


def _header_row(ws, wanted: str, max_scan: int = 10) -> int | None:
    for r in range(1, min(ws.max_row, max_scan) + 1):
        if norm(clean_text(ws.cell(r, 1).value)) == norm(wanted):
            return r
    return None


def _headers(ws, row: int) -> dict[int, str]:
    return {
        c: clean_text(ws.cell(row, c).value)
        for c in range(1, ws.max_column + 1)
        if clean_text(ws.cell(row, c).value)
    }


def _raw_row(ws_values, ws_formulas, r: int, max_col: int) -> dict:
    raw = {}
    for c in range(1, max_col + 1):
        value = ws_values.cell(r, c).value
        formula = ws_formulas.cell(r, c).value
        has_formula = isinstance(formula, str) and formula.startswith("=")
        if value is None and not has_formula:
            continue
        cell = {"value": jsonable(value)}
        if has_formula:
            cell["formula"] = formula
        raw[get_column_letter(c)] = cell
    return raw


def read_lists(ws) -> dict[str, list[str]]:
    header = _header_row(ws, "Work Units") or 4
    lists: dict[str, list[str]] = {}
    for c, title in _headers(ws, header).items():
        values = []
        for r in range(header + 1, ws.max_row + 1):
            text = clean_text(ws.cell(r, c).value)
            if text:
                values.append(text)
        lists[title] = values
    return lists


def read_directory(ws_values, ws_formulas) -> list[ParsedIntern]:
    header = _header_row(ws_values, "Slot") or 4
    cols = {norm(v): c for c, v in _headers(ws_values, header).items()}

    def get(r, name):
        c = cols.get(norm(name))
        return ws_values.cell(r, c).value if c else None

    interns = []
    for r in range(header + 1, ws_values.max_row + 1):
        name = clean_text(get(r, "Intern Name"))
        if not name:
            continue
        sort_raw = get(r, "Sort Order") or get(r, "Slot") or 0
        try:
            sort_order = int(float(sort_raw))
        except (TypeError, ValueError):
            sort_order = 0
        include = clean_text(get(r, "Include in Summary? Y/N")).upper()
        interns.append(
            ParsedIntern(
                name=name,
                sheet_name=clean_text(get(r, "Sheet Name")),
                home_dept=clean_text(get(r, "Home Department")),
                status=clean_text(get(r, "Status")) or "Active",
                start_date=_safe_date(get(r, "Start Date")),
                end_date=_safe_date(get(r, "End Date")),
                notes=clean_text(get(r, "Replacement / Notes")),
                include_in_summary=include.startswith("Y") if include else True,
                sort_order=sort_order,
                row_number=r,
                raw=_raw_row(ws_values, ws_formulas, r, ws_values.max_column),
            )
        )
    return interns


def read_summary(ws) -> tuple[dict[str, float], list[str]]:
    """Cached 'Total Hours' per sheet from the old Summary (used only for reconciliation)."""
    for r in range(1, min(ws.max_row, 40) + 1):
        headers = {norm(clean_text(ws.cell(r, c).value)): c for c in range(1, ws.max_column + 1)}
        if "sheet name" in headers and "total hours" in headers:
            sheet_col, total_col = headers["sheet name"], headers["total hours"]
            units = [
                clean_text(ws.cell(r, c).value)
                for c in range(sheet_col + 1, total_col)
                if clean_text(ws.cell(r, c).value)
            ]
            totals = {}
            for rr in range(r + 1, ws.max_row + 1):
                sheet = clean_text(ws.cell(rr, sheet_col).value)
                if not sheet:
                    if norm(clean_text(ws.cell(rr, 1).value)) == "total":
                        break
                    continue
                value = ws.cell(rr, total_col).value
                if isinstance(value, int | float):
                    totals[sheet] = float(value)
            return totals, units
    return {}, []


def read_log_sheet(ws_values, ws_formulas, intern: ParsedIntern | None) -> list[ParsedRow]:
    header = _header_row(ws_values, "Date")
    if header is None:
        return []
    headers = _headers(ws_values, header)
    cols = {LOG_HEADERS[norm(t)]: c for c, t in headers.items() if norm(t) in LOG_HEADERS}
    known_cols = set(headers)
    max_col = max(ws_values.max_column, max(headers) if headers else 0)

    rows = []
    for r in range(header + 1, ws_values.max_row + 1):

        def val(key, _r=r):
            c = cols.get(key)
            return ws_values.cell(_r, c).value if c else None

        description = clean_text(val("description"))
        date_value = val("date")
        try:
            hours_value = to_number(val("hours"))
            hours_error = False
        except ValueError:
            hours_value, hours_error = None, True
        has_date = date_value is not None and clean_text(date_value) != ""
        # A "real" row has a date, a description, or positive hours. Prefilled template rows
        # (only intern/department/Y-N defaults and a blank duration formula) are skipped.
        if not (has_date or description or (hours_value and hours_value > 0)):
            continue

        row = ParsedRow(
            sheet_name=ws_values.title,
            row_number=r,
            raw=_raw_row(ws_values, ws_formulas, r, max_col),
        )
        row.description = description
        row.intern_name = clean_text(val("intern_name"))
        row.home_dept = clean_text(val("home_dept"))
        row.work_unit = re.sub(r"\s+", " ", clean_text(val("work_unit")))
        row.task_category = clean_text(val("task_category"))
        row.supervisor = clean_text(val("supervisor"))
        row.notes = clean_text(val("notes"))
        row.is_backlog = yes_no(val("backlog"), row)
        row.ai_used = yes_no(val("ai"), row)

        try:
            row.date = to_date(date_value)
        except ValueError:
            row.flag("invalid_date")
        if row.date is None and "invalid_date" not in row.flags:
            row.flag("missing_date")

        for key, attr in (("start", "start"), ("end", "end")):
            try:
                parsed, was_text = to_time(val(key))
                setattr(row, attr, parsed)
                if was_text:
                    row.flag("text_time")
            except ValueError:
                row.flag("invalid_time")

        computed = duration_hours(row.start, row.end) if row.start and row.end else None
        if hours_error:
            row.flag("invalid_hours")
        hours_col = cols.get("hours")
        hours_formula = ws_formulas.cell(r, hours_col).value if hours_col else None
        is_duration_formula = isinstance(hours_formula, str) and hours_formula.startswith("=")
        if hours_value is None:
            if computed is not None:
                # A duration formula without a cached result (file never recalculated) gives
                # the same value Excel would; only hand-blank cells are flagged.
                row.hours = computed
                if not is_duration_formula:
                    row.flag("hours_computed")
            else:
                row.flag("missing_hours")
        else:
            row.hours = hours_value
            if computed is not None and abs(computed - hours_value) > MISMATCH_TOLERANCE:
                row.flag("hours_mismatch")
        if computed is not None and computed > SUSPICIOUS_HOURS:
            row.flag("suspicious_duration")
        if hours_value is not None and (row.start is None) != (row.end is None):
            row.flag("missing_time")

        if not row.work_unit:
            row.flag("missing_work_unit")
        if intern:
            if row.intern_name and norm(row.intern_name) != norm(intern.name):
                row.flag("intern_name_mismatch")
        extra = [
            letter
            for letter, cell in row.raw.items()
            if _col_index(letter) not in known_cols and clean_text(cell.get("value"))
        ]
        if extra:
            row.flag("extra_columns")
        rows.append(row)
    return rows


def _col_index(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n


def _has_data_below_header(ws_values, ws_formulas, header_row: int) -> bool:
    for r in range(header_row + 1, ws_values.max_row + 1):
        for c in range(1, ws_values.max_column + 1):
            formula = ws_formulas.cell(r, c).value
            if isinstance(formula, str) and formula.startswith("="):
                continue
            if clean_text(ws_values.cell(r, c).value):
                return True
    return False


# --------------------------------------------------------------------------- entry point


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_workbook(path: str | Path) -> ParsedWorkbook:
    path = Path(path)
    with warnings.catch_warnings():
        # openpyxl drops Excel's data-validation *extension* (dropdown UI only, no data).
        warnings.filterwarnings("ignore", message="Data Validation extension")
        wb_values = load_workbook(path, data_only=True)
        wb_formulas = load_workbook(path, data_only=False)

    lists = read_lists(wb_values[LISTS_SHEET]) if LISTS_SHEET in wb_values.sheetnames else {}
    interns = (
        read_directory(wb_values[DIRECTORY_SHEET], wb_formulas[DIRECTORY_SHEET])
        if DIRECTORY_SHEET in wb_values.sheetnames
        else []
    )
    summary_hours, summary_units = (
        read_summary(wb_values[SUMMARY_SHEET])
        if SUMMARY_SHEET in wb_values.sheetnames
        else ({}, [])
    )
    by_sheet = {i.sheet_name: i for i in interns if i.sheet_name}

    work_units = {norm(u) for u in lists.get("Work Units", [])}
    parsed = ParsedWorkbook(
        filename=path.name,
        sha256=file_sha256(path),
        lists=lists,
        interns=interns,
        rows={},
        sheets=[],
        summary_hours=summary_hours,
        summary_units=summary_units,
    )

    for name in wb_values.sheetnames:
        ws_v, ws_f = wb_values[name], wb_formulas[name]
        state = ws_v.sheet_state
        if name == LISTS_SHEET:
            parsed.sheets.append(SheetReport(name, state, "lists"))
            continue
        if name == DIRECTORY_SHEET:
            parsed.sheets.append(SheetReport(name, state, "directory", len(interns)))
            continue
        if name == SUMMARY_SHEET:
            parsed.sheets.append(SheetReport(name, state, "summary", note="recomputed by the app"))
            continue

        intern = by_sheet.get(name)
        rows = read_log_sheet(ws_v, ws_f, intern)
        if intern is not None:
            # Home department is an intern attribute, so a differing value is reported once
            # per sheet (raw values stay in each row) instead of flagging every row.
            other_depts = sorted(
                {r.home_dept for r in rows if r.home_dept}
                - {d for d in [intern.home_dept] if d},
                key=norm,
            )
            other_depts = [d for d in other_depts if norm(d) != norm(intern.home_dept)]
            if other_depts:
                count = sum(1 for r in rows if r.home_dept in other_depts)
                parsed.warnings.append(
                    f"'{name}': {count} row(s) give home department "
                    f"{', '.join(repr(d) for d in other_depts)}; the directory says "
                    f"'{intern.home_dept}'. The directory value is used."
                )
            for row in rows:
                if row.work_unit and work_units and norm(row.work_unit) not in work_units:
                    row.flag("nonstandard_work_unit")
            parsed.rows[name] = rows
            parsed.sheets.append(SheetReport(name, state, "intern_log", len(rows)))
            continue

        # Not listed in the directory: make sure we are not leaving data behind.
        header = _header_row(ws_v, "Date")
        if header is not None:
            report = SheetReport(name, state, "other", len(rows))
            if rows:
                report.note = "has task rows but is not in the Intern Directory"
                parsed.warnings.append(
                    f"Sheet '{name}' has {len(rows)} task row(s) but is not listed in the "
                    "Intern Directory."
                )
            else:
                report.note = "no task rows (template/placeholder)"
        else:
            header_row = 4
            has_data = _has_data_below_header(ws_v, ws_f, header_row)
            report = SheetReport(name, state, "other")
            report.note = "contains data that is not imported" if has_data else "empty"
            if has_data:
                parsed.warnings.append(f"Sheet '{name}' contains data that this importer skips.")
        parsed.sheets.append(report)

    for intern in interns:
        if intern.sheet_name and intern.sheet_name not in wb_values.sheetnames:
            parsed.warnings.append(
                f"Directory lists sheet '{intern.sheet_name}' for {intern.name}, "
                "but no such sheet exists."
            )
    return parsed
