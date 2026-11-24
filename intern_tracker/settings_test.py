"""Settings used by the test suite only."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")
os.environ["DJANGO_DEMO_MODE"] = "false"  # tests opt in explicitly with override_settings

from .settings import *  # noqa: E402,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"  # noqa: F405
AXES_ENABLED = False

import warnings  # noqa: E402

warnings.filterwarnings("ignore", message="No directory at")
