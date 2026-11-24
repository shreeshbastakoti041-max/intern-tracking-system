from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class LookupBase(models.Model):
    """Coordinator-maintained dropdown values (replaces the hidden `Lists` sheet)."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(
        default=True, help_text="Inactive values are kept for history but hidden from forms."
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Department(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "home department"


class WorkUnit(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "work unit"


class TaskCategory(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "task category"
        verbose_name_plural = "task categories"


class InternProfile(models.Model):
    """One row per intern (replaces the `Intern Directory` sheet)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FORMER = "former", "Former"
        INCOMING = "incoming", "Incoming"
        PAUSED = "paused", "Paused"
        DO_NOT_TRACK = "do_not_track", "Do Not Track"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intern_profile",
        help_text="Login account. Former interns may have none.",
    )
    display_name = models.CharField(max_length=100)
    home_department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="interns"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    include_in_summary = models.BooleanField(
        default=True, help_text="Include this intern in dashboard and all-intern report totals."
    )
    sort_order = models.PositiveIntegerField(default=0)
    legacy_sheet_name = models.CharField(
        max_length=100, blank=True, help_text="Worksheet name in the original Excel tracker."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "display_name"]

    def __str__(self):
        return self.display_name


class TimeEntryQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The single authorization rule for reading entries."""
        if not user.is_authenticated:
            return self.none()
        if user.can_view_all:
            return self
        return self.filter(intern__user=user)

    def in_range(self, start=None, end=None):
        qs = self
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    def needing_review(self):
        return self.exclude(review_flags=[]).filter(reviewed_at__isnull=True)


class TimeEntry(models.Model):
    """One task / block of work (one row of an intern's Excel tab)."""

    class Source(models.TextChoices):
        APP = "app", "Entered in app"
        IMPORT = "import", "Imported from Excel"

    intern = models.ForeignKey(InternProfile, on_delete=models.PROTECT, related_name="entries")
    date = models.DateField(
        null=True, blank=True, db_index=True, help_text="Required for new entries."
    )
    work_unit = models.ForeignKey(
        WorkUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="entries"
    )
    task_category = models.ForeignKey(
        TaskCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="entries"
    )
    description = models.CharField("task description", max_length=500, blank=True)
    is_backlog = models.BooleanField("backlog work", default=False)
    ai_used = models.BooleanField(
        "AI used", default=False, help_text="An AI workflow materially helped this task."
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    hours = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_entries",
        verbose_name="supervisor / lead",
    )
    supervisor_text = models.CharField(
        "supervisor / lead (legacy text)", max_length=150, blank=True
    )
    notes = models.TextField(blank=True)

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.APP)
    review_flags = models.JSONField(default=list, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()
    objects = TimeEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-start_time", "-id"]
        indexes = [models.Index(fields=["intern", "date"])]
        verbose_name = "time entry"
        verbose_name_plural = "time entries"

    def __str__(self):
        return f"{self.intern} · {self.date or 'no date'} · {self.description[:40]}"

    @property
    def needs_review(self) -> bool:
        return bool(self.review_flags) and self.reviewed_at is None

    @property
    def supervisor_display(self) -> str:
        return str(self.supervisor) if self.supervisor else self.supervisor_text

    def can_edit(self, user) -> bool:
        """Interns edit their own entries; admins edit any; supervisors are read-only."""
        if not user.is_authenticated:
            return False
        if user.is_admin_role:
            return True
        return self.intern.user_id == user.pk
