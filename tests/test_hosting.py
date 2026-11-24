import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from tracking.models import TimeEntry

from .workbook_factory import build


@pytest.fixture
def upload(tmp_path):
    path = build(tmp_path / "tracker.xlsx")

    def make():
        return SimpleUploadedFile("tracker.xlsx", path.read_bytes())

    return make


def test_upload_dry_run_then_save(client, admin_user, upload):
    client.force_login(admin_user)
    resp = client.post(reverse("import_workbook"), {"file": upload()})
    assert resp.status_code == 200 and "Dry run complete" in resp.content.decode()
    assert TimeEntry.objects.count() == 0

    resp = client.post(reverse("import_workbook"), {"file": upload(), "save": "on"})
    assert "Imported 7 entries" in resp.content.decode()
    assert TimeEntry.objects.count() == 7

    resp = client.post(reverse("import_workbook"), {"file": upload(), "save": "on"})
    assert "Replace earlier imports" in resp.content.decode()  # refused, explains how
    assert TimeEntry.objects.count() == 7
    client.post(reverse("import_workbook"), {"file": upload(), "save": "on", "replace": "on"})
    assert TimeEntry.objects.count() == 7


def test_upload_rejects_bad_files(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(reverse("import_workbook"),
                       {"file": SimpleUploadedFile("notes.txt", b"hello")})
    assert "ending in .xlsx" in resp.content.decode()
    resp = client.post(reverse("import_workbook"),
                       {"file": SimpleUploadedFile("fake.xlsx", b"not a workbook")})
    assert "could not be read" in resp.content.decode()


def test_upload_is_admin_only(client, supervisor, upload):
    client.force_login(supervisor)
    assert client.post(reverse("import_workbook"), {"file": upload()}).status_code == 403


def test_ensure_admin(db, monkeypatch, django_user_model):
    call_command("ensure_admin")  # no variables: does nothing
    assert django_user_model.objects.count() == 0
    monkeypatch.setenv("DJANGO_ADMIN_EMAIL", "Coordinator@Example.edu")
    monkeypatch.setenv("DJANGO_ADMIN_PASSWORD", "short")
    call_command("ensure_admin")  # weak password rejected
    assert django_user_model.objects.count() == 0
    monkeypatch.setenv("DJANGO_ADMIN_PASSWORD", "harbor-maple-lantern-42")
    call_command("ensure_admin")
    user = django_user_model.objects.get()
    assert user.email == "coordinator@example.edu" and user.is_admin_role
    assert user.check_password("harbor-maple-lantern-42")
    monkeypatch.setenv("DJANGO_ADMIN_PASSWORD", "different-pass-phrase-99")
    call_command("ensure_admin")  # existing account is never changed
    user.refresh_from_db()
    assert user.check_password("harbor-maple-lantern-42")
