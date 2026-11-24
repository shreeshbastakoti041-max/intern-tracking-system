import os
import subprocess
import sys

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

DEMO = {"DEMO_MODE": True, "DEBUG": True}


@pytest.fixture
def seeded(db):
    call_command("seed_demo")


@pytest.fixture
def client():
    from django.test import Client

    return Client(HTTP_HOST="localhost")  # REMOTE_ADDR defaults to 127.0.0.1


def test_demo_is_off_by_default(client, seeded):
    assert client.get(reverse("demo_home")).status_code == 404
    assert client.post(reverse("demo_login", args=["admin"])).status_code == 404


@override_settings(**DEMO)
def test_demo_login_uses_normal_permissions(client, seeded):
    assert client.get(reverse("demo_home")).status_code == 200
    resp = client.post(reverse("demo_login", args=["supervisor"]))
    assert resp.status_code == 302
    assert client.get(reverse("dashboard")).status_code == 200
    assert client.get(reverse("review_queue")).status_code == 403  # still read-only

    client.post(reverse("demo_login", args=["intern"]))
    assert client.get(reverse("my_log")).status_code == 200
    assert client.get(reverse("dashboard")).status_code == 403

    client.post(reverse("demo_login", args=["admin"]))
    assert client.get(reverse("review_queue")).status_code == 200


@override_settings(**DEMO)
def test_demo_rejects_non_local_requests(client, seeded):
    assert client.get(reverse("demo_home"), REMOTE_ADDR="10.0.0.5").status_code == 404
    assert client.post(reverse("demo_login", args=["admin"]),
                       REMOTE_ADDR="192.168.1.20").status_code == 404


@override_settings(**DEMO, ALLOWED_HOSTS=["localhost", "tracker.example.edu"])
def test_demo_rejects_non_local_host_names(client, seeded):
    assert client.get(reverse("demo_home"), HTTP_HOST="tracker.example.edu").status_code == 404


@override_settings(DEMO_MODE=True, DEBUG=False)
def test_demo_requires_debug(client, seeded):
    assert client.get(reverse("demo_home")).status_code == 404


@override_settings(**DEMO)
def test_demo_login_requires_post(client, seeded):
    assert client.get(reverse("demo_login", args=["admin"])).status_code == 405


def test_demo_users_have_no_usable_password(seeded, django_user_model):
    users = django_user_model.objects.filter(email__endswith="@example.com")
    assert users.count() >= 5
    assert not any(u.has_usable_password() for u in users)


def test_seed_refuses_database_with_real_import(db):
    from imports.models import ImportBatch

    ImportBatch.objects.create(filename="real.xlsx", sha256="x")
    with pytest.raises(Exception, match="refusing"):
        call_command("seed_demo")


def test_settings_refuse_demo_mode_without_debug():
    env = {**os.environ, "DJANGO_DEMO_MODE": "true", "DJANGO_DEBUG": "false",
           "DJANGO_SECRET_KEY": "x" * 50, "DJANGO_SETTINGS_MODULE": "intern_tracker.settings"}
    proc = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0 and "DJANGO_DEMO_MODE requires DJANGO_DEBUG" in proc.stderr


@override_settings(**DEMO)
def test_switching_roles_with_csrf_enforced(seeded):
    from django.test import Client

    browser = Client(HTTP_HOST="localhost", enforce_csrf_checks=True)
    page = browser.get(reverse("demo_home"))
    assert "no-store" in page["Cache-Control"]  # Back button reloads a fresh token
    stale_token = page.context["csrf_token"]
    resp = browser.post(reverse("demo_login", args=["intern"]),
                        {"csrfmiddlewaretoken": stale_token})
    assert resp.status_code == 302

    # Re-using the page from before sign-in is still rejected, with a plain explanation.
    resp = browser.post(reverse("demo_login", args=["supervisor"]),
                        {"csrfmiddlewaretoken": stale_token})
    assert resp.status_code == 403
    assert "That page was out of date" in resp.content.decode()

    # Re-opening the role page (what the Back button now does) works.
    fresh = browser.get(reverse("demo_home")).context["csrf_token"]
    resp = browser.post(reverse("demo_login", args=["supervisor"]),
                        {"csrfmiddlewaretoken": fresh})
    assert resp.status_code == 302
    assert browser.get(reverse("dashboard")).status_code == 200
