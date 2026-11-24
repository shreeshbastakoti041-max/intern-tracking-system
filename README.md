# OSP Intern Tracker

A small Django web app that replaces the Office of Sponsored Programs' Excel-based intern
tracker (`OSP INTERN-TRACKER 3.0.xlsx`).

- **Interns** log tasks, including the date, start and end time, work unit, task category,
  backlog flag, AI-use flag, supervisor and notes. Hours are calculated automatically.
- **Supervisors** see a dashboard (hours by intern × work unit, backlog and AI-assisted hours,
  task counts), filter the full history, and download Excel or CSV reports for one intern or
  all interns over any date range.
- **Admins / coordinators** manage interns, logins and dropdown lists, and review rows
  flagged during the Excel import.

> **Never commit real data.** This is a public repository. Spreadsheets, CSV files, databases
> and `.env` are git-ignored, and CI fails if one is committed. Keep the workbook outside the
> repo (for example in `~/osp-data/`).

## Stack

Python 3.12 · Django 5 · PostgreSQL (SQLite works for local development) · server-rendered
templates · openpyxl · django-filter · django-simple-history (audit trail) · django-axes
(login throttling) · Argon2 password hashing · WhiteNoise + Gunicorn · Docker.

## Local development

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DJANGO_DEBUG=true            # dev only: uses SQLite + console email
python manage.py migrate
python manage.py seed_demo --password 'choose-a-dev-password'   # synthetic demo users and data
python manage.py runserver
```

The demo logins are `admin@example.com`, `supervisor@example.com` and
`intern1@example.com` to `intern3@example.com`, all with the password you chose.

Run the checks:

```bash
pytest
ruff check .
```

## Importing the existing Excel workbook

```bash
# 1. Always start with a dry run. It reads every sheet, prints a reconciliation, saves nothing.
python manage.py import_workbook ~/osp-data/"OSP INTERN-TRACKER 3.0.xlsx" --dry-run

# 2. If the counts and hours match, import it for real.
python manage.py import_workbook ~/osp-data/"OSP INTERN-TRACKER 3.0.xlsx" --user admin@your.edu
```

How the importer preserves data:

- **Nothing is lost.** Every source row is stored verbatim (each cell's value and formula) in
  `ImportedRow.raw`, linked to the entry created from it.
- **Hours are imported exactly as the workbook shows them.** Suspicious rows are flagged, not
  changed. The flags cover AM/PM mix-ups, times typed as text, hand-typed hours that disagree
  with start/end, missing dates, nonstandard work units and directory mismatches.
  Coordinators fix them in **Review**.
- **Nonstandard work units are kept.** Values such as "Scanning Project" become *inactive*
  work units, so their hours still count. They are hidden from the entry form.
- **The run only succeeds if totals match.** It succeeds only when every intern's row count
  and hour total match the workbook. The report also explains where the old Summary sheet
  disagreed: it ignored hours logged under "Other" and nonstandard units.
- **Re-importing is guarded.** The same file can't be imported twice. To load a newer
  workbook at cutover, use `--replace`. That deletes previously *imported* entries only;
  entries typed into the app are kept.

## Accounts and roles

| Role | Can do |
|---|---|
| Intern | Log, edit and delete **their own** entries; see their own summary |
| Supervisor | Read-only access to every intern: dashboard, records, intern pages, reports |
| Admin / Coordinator | Everything, plus **Manage** (Django admin) and the import **Review** queue |

Accounts are invite-only, with no public sign-up. To add someone:

1. In **Manage → Users → Add**, enter their email and role and leave the password blank.
2. Select the user and run **"Send invite / set-password email"**.
3. For interns, open **Manage → Intern profiles** and set the profile's **User**. Imported
   interns already have profiles.

## Configuration

All settings come from environment variables; see [`.env.example`](.env.example). In
production you must set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`, and
`DJANGO_SECURE_SSL=true` when served over HTTPS. Set the `EMAIL_*` variables to send invites;
without them, emails are printed to the console.

## Deployment (any host)

The repo is host-agnostic. With Docker:

```bash
cp .env.example .env    # then edit it
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

On a platform without Docker, use any Python host with PostgreSQL. The build step is
`pip install -r requirements.txt && python manage.py collectstatic --noinput`, the release
step is `python manage.py migrate`, and the web process is
`gunicorn intern_tracker.wsgi:application`.

Back up the PostgreSQL database regularly. It is the system of record after cutover.

## Project layout

```
intern_tracker/   settings (env-driven), urls
accounts/         User model (email login, role), invites, permission decorators
tracking/         models, entry form, intern / supervisor / review views
  services/       hours.py (duration math), periods.py (fiscal quarters), stats.py (all totals)
reports/          Excel / CSV report builders and the report page
imports/          Excel parser (workbook.py), loader + reconciliation (services.py), command
templates/, static/
tests/            pytest suite; tests/workbook_factory.py builds a synthetic workbook
```

## Decisions worth knowing

- **One place for totals.** The dashboard, intern pages and every report use
  `tracking/services/stats.py`, so the numbers always agree.
- **One rule for access.** `TimeEntry.objects.visible_to(user)` controls what each user can
  read: interns get only their own entries. Supervisors are read-only.
- **Hours are always calculated** from start and end time for app entries. The form rejects
  an end time before the start time (the usual AM/PM mistake), overlapping entries and
  future dates.
- **Fiscal quarters follow the University of Idaho fiscal year** (July 1 – June 30, so
  FY26 Q1 = Jul–Sep 2025).
- **Every change to an entry or intern profile is kept** in its history (see Manage).
- **Optional later additions:** Microsoft (UIdaho) single sign-on, PDF reports, and the
  unused *Special Projects* / *Backlog Snapshot* sheets.
