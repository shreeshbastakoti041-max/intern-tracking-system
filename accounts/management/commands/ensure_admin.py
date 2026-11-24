"""Create the first administrator from environment variables (for hosts without a shell).

Set DJANGO_ADMIN_EMAIL and DJANGO_ADMIN_PASSWORD as secret environment variables on the
host. The account is created once; an existing account is never modified, so the
variables can (and should) be removed after the first sign-in.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the first admin from DJANGO_ADMIN_EMAIL / DJANGO_ADMIN_PASSWORD if missing."

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_ADMIN_PASSWORD", "")
        if not email or not password:
            self.stdout.write("ensure_admin: no DJANGO_ADMIN_EMAIL/PASSWORD set; skipping.")
            return
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write("ensure_admin: admin account already exists; nothing changed.")
            return
        candidate = User(email=email, role=User.Role.ADMIN)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            self.stderr.write("ensure_admin: password rejected: " + " ".join(exc.messages))
            return
        User.objects.create_superuser(email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"ensure_admin: created admin account {email}."))
