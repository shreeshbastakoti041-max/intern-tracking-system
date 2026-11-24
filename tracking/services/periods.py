"""Date-range presets. University of Idaho fiscal year starts July 1 (FY26 = Jul 2025-Jun 2026)."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: date | None
    end: date | None
    kind: str = "other"  # "quarter" for the fiscal-year track, "fy", or "other"
    is_current: bool = False
    is_future: bool = False


def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 7 else d.year


def fiscal_quarter(d: date) -> tuple[int, int]:
    return fiscal_year(d), (d.month - 7) % 12 // 3 + 1


def quarter_range(fy: int, quarter: int) -> tuple[date, date]:
    month = 7 + 3 * (quarter - 1)
    year = fy - 1
    if month > 12:
        month -= 12
        year += 1
    start = date(year, month, 1)
    end_month, end_year = month + 3, year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    return start, date(end_year, end_month, 1) - timedelta(days=1)


def week_range(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def fy_label(fy: int) -> str:
    return f"FY{fy % 100:02d}"


def presets(today: date) -> list[Period]:
    fy, current_q = fiscal_quarter(today)
    week_start, week_end = week_range(today)
    items = [
        Period("week", "This week", week_start, week_end),
        Period("month", "This month", today.replace(day=1), today),
    ]
    for q in (1, 2, 3, 4):
        start, end = quarter_range(fy, q)
        items.append(
            Period(f"q{q}", f"{fy_label(fy)} Q{q}", start, end, kind="quarter",
                   is_current=q == current_q, is_future=q > current_q)
        )
    items += [
        Period("fy", fy_label(fy), date(fy - 1, 7, 1), date(fy, 6, 30), kind="fy",
               is_current=True),
        Period("prev_fy", fy_label(fy - 1), date(fy - 2, 7, 1), date(fy - 1, 6, 30), kind="fy"),
        Period("all", "All time", None, None),
    ]
    return items


def current_quarter_key(today: date) -> str:
    return f"q{fiscal_quarter(today)[1]}"
