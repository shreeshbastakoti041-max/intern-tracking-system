"""Duration math shared by the entry form and the Excel importer."""

from datetime import time
from decimal import ROUND_HALF_UP, Decimal

HOURS_PLACES = Decimal("0.0001")
SECONDS_PER_DAY = 24 * 60 * 60


def _seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def duration_hours(start: time, end: time) -> Decimal:
    """Hours between two clock times.

    Matches the workbook formula `MOD(End - Start, 1) * 24`: an end time earlier
    than the start time wraps past midnight instead of going negative.
    """
    seconds = (_seconds(end) - _seconds(start)) % SECONDS_PER_DAY
    return to_hours(Decimal(seconds) / Decimal(3600))


def to_hours(value) -> Decimal:
    """Normalize a number to the stored hour precision (4 decimal places)."""
    return Decimal(str(value)).quantize(HOURS_PLACES, rounding=ROUND_HALF_UP)


def overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """True when two same-day time ranges overlap (touching ends do not count)."""
    return a_start < b_end and b_start < a_end
