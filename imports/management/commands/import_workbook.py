from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from imports.services import ImportRefused, run_import
from imports.workbook import parse_workbook
from tracking.flags import flag_label


class Command(BaseCommand):
    help = (
        "Import the legacy OSP Intern Tracker Excel workbook. Every row is kept verbatim; "
        "questionable values are flagged for review instead of being changed."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the .xlsx file (keep it outside the repo).")
        parser.add_argument(
            "--dry-run", action="store_true", help="Do everything, print the report, save nothing."
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete previously imported entries first (entries typed into the app are kept).",
        )
        parser.add_argument(
            "--force", action="store_true", help="Allow importing a file that was imported before."
        )
        parser.add_argument("--user", help="Email of the admin running the import (for audit).")

    def handle(self, *args, **opts):
        path = Path(opts["path"]).expanduser()
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        user = None
        if opts["user"]:
            user = get_user_model().objects.filter(email__iexact=opts["user"]).first()
            if user is None:
                raise CommandError(f"No user with email {opts['user']}")

        self.stdout.write(f"Reading {path.name} …")
        parsed = parse_workbook(path)

        try:
            result = run_import(
                parsed,
                user=user,
                dry_run=opts["dry_run"],
                replace=opts["replace"],
                force=opts["force"],
            )
        except ImportRefused as exc:
            if exc.result is not None:
                self._report(parsed, exc.result)
            raise CommandError(str(exc)) from exc

        self._report(parsed, result)
        if result.dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN — nothing was saved."))
        else:
            message = f"\nImported {result.entries} entries (batch #{result.batch_id})."
            self.stdout.write(self.style.SUCCESS(message))

    def _report(self, parsed, result):
        w = self.stdout.write
        w("\nSheets")
        for s in parsed.sheets:
            note = f" — {s.note}" if s.note else ""
            rows = f"{s.real_rows} rows" if s.kind == "intern_log" else s.kind
            w(f"  {s.name:<32} [{s.state}] {rows}{note}")

        w("\nReconciliation (Excel vs database)")
        w(
            f"  {'Intern':<12}{'Rows XL':>8}{'Rows DB':>8}{'Hours XL':>11}{'Hours DB':>11}"
            f"{'Old Summ.':>11}{'Flagged':>9}  Status / note"
        )
        for r in result.per_intern:
            old = f"{r.old_summary_hours:.2f}" if r.old_summary_hours is not None else "—"
            status = self.style.SUCCESS("OK") if r.ok else self.style.ERROR("MISMATCH")
            w(
                f"  {r.intern:<12}{r.excel_rows:>8}{r.imported_rows:>8}{r.excel_hours:>11.2f}"
                f"{r.db_hours:>11.2f}{old:>11}{r.flagged:>9}  {status} {r.explanation}"
            )
        w(
            f"  {'TOTAL':<12}{result.entries:>8}{'':>8}{'':>11}{result.total_hours:>11.2f}"
            f"{'':>11}{result.flagged:>9}"
        )

        if result.flag_counts:
            w("\nReview flags")
            for code, n in sorted(result.flag_counts.items(), key=lambda kv: -kv[1]):
                w(f"  {n:>5}  {flag_label(code)}")
        if result.created_lookups:
            w("\nLookup values created")
            for kind, names in result.created_lookups.items():
                w(f"  {kind}: {', '.join(names)}")
        if result.replaced_entries:
            w(f"\nReplaced {result.replaced_entries} previously imported entries")
            if result.edited_since_import:
                w(
                    self.style.WARNING(
                        f"  {result.edited_since_import} of them had been edited in the app."
                    )
                )
        for warning in result.warnings:
            w(self.style.WARNING(f"Warning: {warning}"))
