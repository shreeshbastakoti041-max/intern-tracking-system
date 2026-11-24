from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Department, InternProfile, TaskCategory, TimeEntry, WorkUnit


class LookupAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    search_fields = ["name"]


admin.site.register(Department, LookupAdmin)
admin.site.register(WorkUnit, LookupAdmin)
admin.site.register(TaskCategory, LookupAdmin)


@admin.register(InternProfile)
class InternProfileAdmin(SimpleHistoryAdmin):
    list_display = [
        "display_name", "home_department", "status", "user", "include_in_summary",
        "start_date", "end_date", "sort_order",
    ]
    list_filter = ["status", "home_department", "include_in_summary"]
    list_editable = ["status", "include_in_summary", "sort_order"]
    search_fields = ["display_name", "user__email", "legacy_sheet_name"]
    autocomplete_fields = ["user"]


@admin.register(TimeEntry)
class TimeEntryAdmin(SimpleHistoryAdmin):
    list_display = [
        "date", "intern", "work_unit", "description", "hours", "is_backlog", "ai_used",
        "source", "needs_review",
    ]
    list_filter = ["source", "work_unit", "is_backlog", "ai_used", "intern"]
    search_fields = ["description", "notes", "supervisor_text", "intern__display_name"]
    date_hierarchy = "date"
    autocomplete_fields = ["intern", "supervisor"]
    readonly_fields = ["source", "review_flags", "created_by", "created_at", "updated_at"]
    list_select_related = ["intern", "work_unit"]

    @admin.display(boolean=True)
    def needs_review(self, obj):
        return obj.needs_review
