#!/bin/sh
# Local preview with synthetic data. Uses its own database (demo.sqlite3) and only
# listens on this computer. Never use this for a real deployment.
set -e
cd "$(dirname "$0")/.."
export DJANGO_DEBUG=true DJANGO_DEMO_MODE=true
unset DATABASE_URL
PORT="${PORT:-8000}"
.venv/bin/python manage.py migrate --noinput -v0
.venv/bin/python manage.py seed_demo
echo "Demo running at http://127.0.0.1:${PORT}/demo/"
exec .venv/bin/python manage.py runserver "127.0.0.1:${PORT}"
