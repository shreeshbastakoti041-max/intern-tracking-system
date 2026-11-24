from datetime import date, time
from decimal import Decimal
from io import BytesIO

from django.urls import reverse
from openpyxl import load_workbook


def _download(client, **params):
    resp = client.get(reverse("reports"), {"download": "1", **params})
    assert resp.status_code == 200, resp.content[:500]
    return resp


def test_all_interns_report_totals_match(client, supervisor, intern_a, intern_b, make_entry):
    make_entry(intern_a, unit="Finance")
    make_entry(intern_a, unit="Other", start=time(10), end=time(12, 15))
    make_entry(intern_b, unit="Pre-Award", day=date(2026, 2, 1))
    make_entry(intern_b, unit="Pre-Award", day=date(2027, 1, 1))  # outside range
    client.force_login(supervisor)
    resp = _download(client, scope="all", file_format="xlsx", start="2026-01-01",
                     end="2026-12-31")
    wb = load_workbook(BytesIO(resp.content))
    ws = wb["Summary"]
    values = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
    assert Decimal(str(values["Total hours"])) == Decimal("4.25")
    assert values["Tasks"] == 3
    assert wb["Entries"].max_row == 4  # header + 3


def test_single_intern_report(client, supervisor, intern_a, intern_b, make_entry):
    make_entry(intern_a)
    make_entry(intern_b)
    client.force_login(supervisor)
    resp = _download(client, scope="intern", intern=intern_a.pk, file_format="xlsx")
    assert "alpha-report" in resp["Content-Disposition"]
    wb = load_workbook(BytesIO(resp.content))
    assert wb["Entries"].max_row == 2
    assert wb["Summary"]["A1"].value.endswith("Alpha")


def test_excluded_interns_left_out_unless_requested(client, supervisor, intern_a, intern_b,
                                                    make_entry):
    intern_b.include_in_summary = False
    intern_b.save()
    make_entry(intern_a)
    make_entry(intern_b)
    client.force_login(supervisor)
    body = b"".join(_download(client, scope="all", file_format="csv").streaming_content)
    assert body.decode().count("\n") == 2
    body = b"".join(_download(client, scope="all", file_format="csv",
                              include_excluded="on").streaming_content)
    assert body.decode().count("\n") == 3


def test_intern_scope_requires_intern(client, supervisor):
    client.force_login(supervisor)
    resp = client.get(reverse("reports"), {"download": "1", "scope": "intern",
                                           "file_format": "xlsx"})
    assert resp.status_code == 200 and "Choose an intern" in resp.content.decode()
