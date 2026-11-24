"""Local-only demo mode: one-click sign-in as synthetic demo users.

This does not bypass authentication or permissions. It signs the browser in as one of
the seeded demo accounts (which have no usable password), and every page then applies
the normal role checks. Every view here returns 404 unless all of these hold:

* settings.DEMO_MODE is true (off by default),
* settings.DEBUG is true (enforced again at startup in settings.py),
* the request comes from this computer (loopback address and localhost host name).
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.http import Http404
from django.http.request import split_domain_port
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

LOOPBACK_ADDRS = {"127.0.0.1", "::1"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}

DEMO_ACCOUNTS = {
    "admin": {
        "email": "admin@example.com",
        "label": "Coordinator",
        "summary": (
            "Everything a supervisor sees, plus checking imported Excel rows and managing "
            "people, sign-ins and dropdown lists."
        ),
    },
    "supervisor": {
        "email": "supervisor@example.com",
        "label": "Supervisor",
        "summary": (
            "Follows every intern's hours by quarter and work unit, filters records and "
            "downloads reports. Can't change entries."
        ),
    },
    "intern": {
        "email": "intern1@example.com",
        "label": "Intern",
        "summary": (
            "Logs tasks in a weekly time log and sees their own hours. "
            "Can't see other interns."
        ),
    },
}


def is_demo_request(request) -> bool:
    if not (getattr(settings, "DEMO_MODE", False) and settings.DEBUG):
        return False
    if request.META.get("REMOTE_ADDR") not in LOOPBACK_ADDRS:
        return False
    host, _ = split_domain_port(request.get_host())
    return host in LOCAL_HOSTS


def demo_context(request):
    return {"demo_mode": is_demo_request(request)}


@never_cache  # Back button must reload it, so its security token is never stale
def demo_home(request):
    if not is_demo_request(request):
        raise Http404
    User = get_user_model()
    accounts = []
    for role, info in DEMO_ACCOUNTS.items():
        accounts.append(
            {**info, "role": role, "ready": User.objects.filter(email=info["email"]).exists()}
        )
    return render(request, "accounts/demo.html", {"accounts": accounts})


@require_POST
def demo_login(request, role):
    if not is_demo_request(request) or role not in DEMO_ACCOUNTS:
        raise Http404
    user = get_user_model().objects.filter(
        email=DEMO_ACCOUNTS[role]["email"], role=role, is_active=True
    ).first()
    if user is None:
        messages.error(request, "Demo data is missing. Start the demo with scripts/run_demo.sh.")
        return redirect("demo_home")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    label = DEMO_ACCOUNTS[role]["label"].lower()
    messages.info(request, f"You're now viewing as the demo {label}.")
    return redirect("home")
