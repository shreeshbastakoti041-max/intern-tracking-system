from datetime import date, time
from decimal import Decimal

from tracking.services.hours import duration_hours, overlaps
from tracking.services.periods import fiscal_quarter, presets, quarter_range


def test_duration_simple():
    assert duration_hours(time(9), time(10, 30)) == Decimal("1.5000")


def test_duration_wraps_midnight_like_excel_mod():
    # MOD(End-Start,1)*24: 12:45 -> 2:15 is 13.5 h, not negative
    assert duration_hours(time(12, 45), time(2, 15)) == Decimal("13.5000")


def test_duration_same_time_is_zero():
    assert duration_hours(time(9), time(9)) == Decimal("0.0000")


def test_overlaps():
    assert overlaps(time(9), time(10), time(9, 30), time(11))
    assert not overlaps(time(9), time(10), time(10), time(11))  # touching is fine


def test_fiscal_quarters_start_in_july():
    assert fiscal_quarter(date(2025, 7, 1)) == (2026, 1)
    assert fiscal_quarter(date(2025, 12, 31)) == (2026, 2)
    assert fiscal_quarter(date(2026, 1, 1)) == (2026, 3)
    assert fiscal_quarter(date(2026, 6, 30)) == (2026, 4)
    assert quarter_range(2026, 1) == (date(2025, 7, 1), date(2025, 9, 30))
    assert quarter_range(2026, 2) == (date(2025, 10, 1), date(2025, 12, 31))
    assert quarter_range(2026, 4) == (date(2026, 4, 1), date(2026, 6, 30))


def test_presets_labels():
    periods = {p.key: p for p in presets(date(2026, 11, 24))}
    assert periods["q2"].label == "FY27 Q2" and periods["q2"].is_current
    assert periods["q3"].is_future and not periods["q1"].is_future
    assert periods["fy"].label == "FY27" and periods["prev_fy"].label == "FY26"
