"""Human-readable labels for review flags set by the Excel importer."""

FLAG_LABELS = {
    "missing_date": "No date in Excel",
    "invalid_date": "Date could not be read",
    "text_time": "Time was typed as text, such as 1:00PM",
    "invalid_time": "Start/end time could not be read",
    "missing_time": "Start or end time missing",
    "hours_mismatch": "Hours don't match start/end times",
    "suspicious_duration": "Start to end is over 12 hours, likely an AM/PM mix-up",
    "hours_computed": "Hours were blank; computed from start/end",
    "missing_hours": "No hours recorded",
    "invalid_hours": "Hours value could not be read",
    "missing_work_unit": "No work unit",
    "nonstandard_work_unit": "Work unit not in the standard list",
    "intern_name_mismatch": "Intern name differs from the directory",
    "home_dept_mismatch": "Home department differs from the directory",
    "invalid_yes_no": "Backlog or AI value wasn't Y or N",
    "extra_columns": "Data found outside the standard columns",
}


def flag_label(code: str) -> str:
    return FLAG_LABELS.get(code, code.replace("_", " ").capitalize())
