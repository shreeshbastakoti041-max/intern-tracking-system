"""Create synthetic demo data for local preview. Never uses real intern data."""

import random
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from imports.models import ImportBatch
from tracking.models import Department, InternProfile, TaskCategory, TimeEntry, WorkUnit
from tracking.services.hours import duration_hours

DEPARTMENTS = ["Pre-Award", "Post-Award", "Finance", "Systems & Data", "UCM", "Admin", "Other"]
WORK_UNITS = ["Admin", "Pre-Award", "Post-Award", "Finance", "Systems & Data", "UCM", "Training",
              "Special Projects", "Other"]
CATEGORIES = ["Standard Task", "Backlog Task", "Training", "Meeting", "Special Project",
              "Documentation", "Data Cleanup", "Other"]
TASKS = {
    "Pre-Award": ["Proposal routing review", "Budget justification check", "Sponsor guideline "
                  "summary", "Rejected proposals cleanup"],
    "Post-Award": ["Award setup", "PPR folder update", "Subaward file review", "Closeout memo"],
    "Finance": ["Closeouts", "Cost transfers", "Scanning project", "Invoice reconciliation"],
    "Systems & Data": ["Data cleanup", "Scanning project", "Report query update", "Dashboard QA"],
    "Admin": ["Email and calendar", "Tracker audit", "Onboarding paperwork"],
    "Training": ["NCURA module", "Required annual training", "1:1 with supervisor"],
    "Other": ["Misc. support"],
}

# (first name, home dept, has login, status, include in summary)
INTERNS = [
    ("Alex Rivera", "Pre-Award", True, "active", True),
    ("Jordan Lee", "Finance", True, "active", True),
    ("Sam Patel", "Systems & Data", True, "active", True),
    ("Morgan Diaz", "Post-Award", False, "former", True),
    ("Taylor Kim", "Finance", False, "paused", False),
]

# Synthetic rows that look like flagged Excel imports, so the review queue has content.
FLAGGED = [
    ("hours_mismatch", "suspicious_duration"),
    ("text_time",),
    ("missing_date",),
    ("nonstandard_work_unit",),
]


def seed_lookups():
    for model, names in ((Department, DEPARTMENTS), (WorkUnit, WORK_UNITS),
                         (TaskCategory, CATEGORIES)):
        for i, name in enumerate(names, start=1):
            model.objects.get_or_create(name=name, defaults={"sort_order": i * 10})


class Command(BaseCommand):
    help = "Create demo users and synthetic entries (local preview only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Optional password for the demo users. Omit it to create them without a "
                 "usable password (demo mode signs in with one click).",
        )
        parser.add_argument("--lookups-only", action="store_true",
                            help="Only create the standard dropdown values.")

    @transaction.atomic
    def handle(self, *args, password=None, lookups_only=False, **opts):
        if ImportBatch.objects.exists():
            raise CommandError(
                "This database contains imported Excel data; refusing to mix in demo data. "
                "Use demo mode (scripts/run_demo.sh), which has its own database."
            )
        seed_lookups()
        if lookups_only:
            self.stdout.write(self.style.SUCCESS("Dropdown values ready."))
            return

        User = get_user_model()

        def user(email, role, first, last=""):
            u, created = User.objects.get_or_create(
                email=email, defaults={"role": role, "first_name": first, "last_name": last}
            )
            if created:
                if password:
                    u.set_password(password)
                else:
                    u.set_unusable_password()
                u.save()
            return u

        user("admin@example.com", "admin", "Demo", "Coordinator")
        supervisor = user("supervisor@example.com", "supervisor", "Demo", "Supervisor")
        user("lead@example.com", "supervisor", "Demo", "Team Lead")

        rng = random.Random(2026)
        today = timezone.localdate()
        units = {u.name: u for u in WorkUnit.objects.all()}
        categories = list(TaskCategory.objects.filter(is_active=True))
        legacy_unit, _ = WorkUnit.objects.get_or_create(
            name="Scanning Project", defaults={"is_active": False, "sort_order": 1000}
        )
        created_entries = 0

        for i, (name, dept, has_login, status, include) in enumerate(INTERNS, start=1):
            account = user(f"intern{i}@example.com", "intern", *name.split(" ", 1)) \
                if has_login else None
            profile, made = InternProfile.objects.get_or_create(
                display_name=name,
                defaults={
                    "user": account,
                    "home_department": Department.objects.get(name=dept),
                    "status": status,
                    "include_in_summary": include,
                    "sort_order": i,
                    "start_date": today - timedelta(days=200),
                    "end_date": today - timedelta(days=40) if status == "former" else None,
                },
            )
            if not made and profile.entries.exists():
                continue
            last_day = profile.end_date or today
            for days_ago in range(200, -1, -1):
                day = today - timedelta(days=days_ago)
                if day > last_day or day.weekday() >= 5 or rng.random() < 0.25:
                    continue
                minutes = 8 * 60 + rng.choice([0, 30, 60])
                for _ in range(rng.randint(1, 3)):
                    length = rng.choice([30, 60, 90, 120, 180])
                    start = time(minutes // 60, minutes % 60)
                    minutes += length
                    end = time(minutes // 60, minutes % 60)
                    minutes += rng.choice([0, 15, 30])
                    unit_name = dept if rng.random() < 0.65 else rng.choice(
                        ["Admin", "Training", "Other", "Special Projects"])
                    tasks = TASKS.get(unit_name) or TASKS["Other"]
                    TimeEntry.objects.create(
                        intern=profile, date=day, start_time=start, end_time=end,
                        hours=duration_hours(start, end), work_unit=units[unit_name],
                        task_category=rng.choice(categories) if rng.random() < 0.5 else None,
                        description=rng.choice(tasks), is_backlog=rng.random() < 0.3,
                        ai_used=rng.random() < 0.15, supervisor=supervisor,
                        created_by=account,
                    )
                    created_entries += 1
            for n, flags in enumerate(FLAGGED):
                day = None if "missing_date" in flags else today - timedelta(days=150 + n)
                start, end = (time(12, 45), time(2, 15)) if "suspicious_duration" in flags \
                    else (time(13), time(15))
                TimeEntry.objects.create(
                    intern=profile, date=day, start_time=start, end_time=end,
                    hours=1.5 if "hours_mismatch" in flags else duration_hours(start, end),
                    work_unit=legacy_unit if "nonstandard_work_unit" in flags
                    else units[dept],
                    description=rng.choice(TASKS[dept]),
                    source=TimeEntry.Source.IMPORT, review_flags=list(flags),
                    supervisor_text="Demo Supervisor",
                )
                created_entries += 1

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready ({created_entries} new synthetic entries). Accounts: "
            "admin@example.com, supervisor@example.com, intern1-3@example.com"
        ))
