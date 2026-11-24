"""Build a small synthetic workbook with the same layout as the real OSP tracker.

All names are fictional. It reproduces the real file's quirks: hidden Lists sheet,
INDIRECT-style Summary that ignores some work units, prefilled blank rows, a text time,
an AM/PM mix-up, hand-typed hours, a missing date, "Y " with a trailing space, a
nonstandard work unit, a home-department typo, and an empty template sheet.
"""

from datetime import date, datetime, time

from openpyxl import Workbook

HEADERS = ["Date", "Intern Name", "Home Department", "Work Unit", "Task/Backlog Description",
           "Backlog Y/N", "AI Use Y/N", "Duration (hrs)", "Start Time", "End Time",
           "Supervisor/Lead", "Notes"]
DURATION = '=IF(AND(I{r}<>"",J{r}<>""),MOD(J{r}-I{r},1)*24,"")'


def _log_sheet(wb, title, rows, prefill=None, blank_rows=3):
    ws = wb.create_sheet(title)
    ws["A1"] = f"{title} Task Log"
    for c, h in enumerate(HEADERS, start=1):
        ws.cell(4, c, h)
    r = 5
    for row in rows:
        for c, value in enumerate(row, start=1):
            if c == 8 and value == "F":
                value = DURATION.format(r=r)
            ws.cell(r, c, value)
        r += 1
    for _ in range(blank_rows):  # prefilled template rows, no real data
        for c, value in (prefill or {}).items():
            ws.cell(r, c, value)
        ws.cell(r, 8, DURATION.format(r=r))
        r += 1
    return ws


def build(path):
    wb = Workbook()
    lists = wb.active
    lists.title = "Lists"
    lists.sheet_state = "hidden"
    lists_cols = {
        "Work Units": ["Admin", "Pre-Award", "Finance", "Systems & Data", "Training", "Other"],
        "Task Categories": ["Standard Task", "Meeting"],
        "Home Departments": ["Pre-Award", "Finance", "Systems & Data"],
    }
    for c, (title, values) in enumerate(lists_cols.items(), start=1):
        lists.cell(4, c, title)
        for r, v in enumerate(values, start=5):
            lists.cell(r, c, v)

    d = wb.create_sheet("Intern Directory")
    for c, h in enumerate(["Slot", "Intern Name", "Sheet Name", "Home Department", "Status",
                           "Start Date", "End Date", "Replacement / Notes",
                           "Include in Summary? Y/N", "Table Name", "Sort Order"], start=1):
        d.cell(4, c, h)
    d.append([1, "Robin", "Robin - Finance", "Finance", "Active", None, None, "", "Y", "tbl_R", 1])
    d.append([2, "Casey", "Casey - Data", "Systems & Data", "Former", None, None, "Left", "Y",
              "tbl_C", 2])
    d.append([3, None, None, None, "Do Not Track", None, None, None, "N", None, 3])

    s = wb.create_sheet("Summary")
    for c, h in enumerate(["Intern", "Sheet Name", "Admin", "Finance", "Total Hours"], start=1):
        s.cell(10, c, h)
    s.append(["Robin", "Robin - Finance", 1.0, 3.0, 4.0])   # ignores the "Other" hour
    s.append(["Casey", "Casey - Data", 0, 0, 0])
    s.cell(13, 1, "Total")

    _log_sheet(wb, "Robin - Finance", [
        # normal formula row: 9:00-10:00 = 1h
        [datetime(2026, 1, 5), "Robin", "Finance", "Admin", "Training docs", "N", "N", "F",
         time(9), time(10), "Pat", ""],
        # backlog with trailing space, 10:00-12:30
        [datetime(2026, 1, 5), "Robin", "Finance", "Finance", "Closeouts", "Y ", "Y", "F",
         time(10), time(12, 30), "", "note here"],
        # "Other" work unit, ignored by old Summary
        [datetime(2026, 1, 6), "Robin", "Finance", "Other", "Misc", "N", "N", "F",
         time(13), time(14), "", ""],
        # missing date
        [None, "Robin", "Finance", "Finance", "Undated task", "N", "N", "F",
         time(8), time(8, 30), "", ""],
    ], prefill={2: "Robin", 3: "Finance", 6: "N", 7: "N"})

    _log_sheet(wb, "Casey - Data", [
        # text times typed by hand + hand-typed hours
        [datetime(2026, 2, 2), "Casey", "Systems & Data", "Systems & Data", "Scanning", "Y", "N",
         2, "1:00PM", "3:00PM", "", ""],
        # AM/PM mix-up: 12:45 -> 2:15 (AM) computes 13.5h, typed 1.5
        [datetime(2026, 2, 3), "Casey", "Coodinator", "Systems & Data", "Review", "Y", "N", 1.5,
         time(12, 45), time(2, 15), "", ""],
        # nonstandard work unit
        [date(2026, 2, 4), "Casey", "Systems & Data", "Scanning Project", "Scan batch", "N", "Y",
         "F", time(9), time(11), "", ""],
    ])

    empty = _log_sheet(wb, "Template - Intern", [], blank_rows=5)
    empty.sheet_state = "hidden"
    wb.save(path)
    return path


# Expected values after import (hours as the workbook stores them).
EXPECTED = {
    "Robin - Finance": {"rows": 4, "hours": "5.0000"},  # 1 + 2.5 + 1 + 0.5
    "Casey - Data": {"rows": 3, "hours": "5.5000"},     # 2 + 1.5 + 2
}
