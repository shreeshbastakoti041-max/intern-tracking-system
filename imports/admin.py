from django.contrib import admin

from .models import ImportBatch, ImportedRow


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ImportBatch)
class ImportBatchAdmin(ReadOnlyAdmin):
    list_display = ["filename", "created_at", "entry_count", "flagged_count", "total_hours"]


@admin.register(ImportedRow)
class ImportedRowAdmin(ReadOnlyAdmin):
    list_display = ["sheet_name", "row_number", "batch", "entry"]
    list_filter = ["sheet_name", "batch"]
