import logging
import os
import tempfile

from django.shortcuts import render

from accounts.permissions import admin_required

from .forms import WorkbookUploadForm
from .services import ImportRefused, run_import
from .workbook import parse_workbook

log = logging.getLogger(__name__)


@admin_required
def upload_workbook(request):
    """Upload the Excel tracker, check it, and (optionally) import it.

    The file is written to a private temporary file only while it is read, then deleted.
    """
    form = WorkbookUploadForm(request.POST or None, request.FILES or None)
    context = {"form": form}
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        try:
            with os.fdopen(fd, "wb") as tmp:
                for chunk in upload.chunks():
                    tmp.write(chunk)
            parsed = parse_workbook(path)
            parsed.filename = os.path.basename(upload.name)
        except Exception:  # unreadable or not the tracker workbook
            log.exception("Workbook upload could not be read")
            context["error"] = (
                "This file could not be read as the intern tracker workbook. Check that it "
                "is the .xlsx file with the Intern Directory and intern tabs."
            )
            return render(request, "imports/upload.html", context)
        finally:
            if os.path.exists(path):
                os.remove(path)

        save = form.cleaned_data["save"]
        replace = form.cleaned_data["replace"]
        context["parsed"] = parsed
        try:
            context["result"] = run_import(
                parsed, user=request.user, dry_run=not save, replace=replace, force=replace
            )
        except ImportRefused as exc:
            context["error"] = str(exc).replace("--replace", "“Replace earlier imports”").replace(
                "Use --force to import it again (together with “Replace earlier imports” to "
                "avoid duplicates).",
                "Tick “Replace earlier imports” to import it again.",
            )
            context["result"] = exc.result
    return render(request, "imports/upload.html", context)
