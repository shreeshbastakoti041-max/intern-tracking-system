from django.conf import settings
from django.db import models

from tracking.models import TimeEntry


class ImportBatch(models.Model):
    """One run of `import_workbook` against one Excel file."""

    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    entry_count = models.PositiveIntegerField(default=0)
    flagged_count = models.PositiveIntegerField(default=0)
    total_hours = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    reconciliation = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "import batches"

    def __str__(self):
        return f"{self.filename} ({self.created_at:%Y-%m-%d %H:%M})"


class ImportedRow(models.Model):
    """An exact copy of one Excel row (every cell value and formula), so nothing is lost."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    sheet_name = models.CharField(max_length=100)
    row_number = models.PositiveIntegerField()
    raw = models.JSONField()
    entry = models.OneToOneField(
        TimeEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="imported_row"
    )

    class Meta:
        ordering = ["sheet_name", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "sheet_name", "row_number"], name="unique_row_per_batch"
            )
        ]

    def __str__(self):
        return f"{self.sheet_name}!{self.row_number}"
