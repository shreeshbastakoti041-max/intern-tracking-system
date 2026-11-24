"""All aggregations live here so the dashboard, summaries and exports always agree.

Unlike the old Excel Summary, every work unit is counted (including "Other",
inactive legacy units and entries with no unit) and only real entries are counted.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from ..models import WorkUnit

ZERO = Decimal("0")
NO_UNIT = "(no work unit)"


def _sum(expr_filter=None):
    return Coalesce(
        Sum("hours", filter=expr_filter),
        Value(ZERO),
        output_field=DecimalField(max_digits=12, decimal_places=4),
    )


def summarize(qs) -> dict:
    """Headline KPIs, mirroring the Summary sheet's top row."""
    agg = qs.order_by().aggregate(
        total_hours=_sum(),
        backlog_hours=_sum(Q(is_backlog=True)),
        ai_hours=_sum(Q(ai_used=True)),
        task_count=Count("id"),
        backlog_task_count=Count("id", filter=Q(is_backlog=True)),
        ai_task_count=Count("id", filter=Q(ai_used=True)),
    )
    return agg


def _ordered_units(names: set[str]) -> list[str]:
    known = list(WorkUnit.objects.order_by("-is_active", "sort_order", "name").values_list(
        "name", flat=True
    ))
    ordered = [n for n in known if n in names]
    ordered += sorted(n for n in names if n not in known and n != NO_UNIT)
    if NO_UNIT in names:
        ordered.append(NO_UNIT)
    return ordered


def hours_by_unit(qs) -> list[dict]:
    rows = qs.order_by().values("work_unit__name").annotate(hours=_sum(), tasks=Count("id"))
    by_name = {(r["work_unit__name"] or NO_UNIT): r for r in rows}
    return [
        {"unit": name, "hours": by_name[name]["hours"], "tasks": by_name[name]["tasks"]}
        for name in _ordered_units(set(by_name))
    ]


@dataclass
class MatrixRow:
    intern_id: int
    intern: str
    cells: list[Decimal]
    total: Decimal
    tasks: int
    backlog_hours: Decimal = ZERO
    ai_hours: Decimal = ZERO
    ai_tasks: int = 0


@dataclass
class Matrix:
    units: list[str]
    rows: list[MatrixRow] = field(default_factory=list)
    unit_totals: list[Decimal] = field(default_factory=list)
    grand_total: Decimal = ZERO

    @property
    def unit_breakdown(self) -> list[tuple[str, Decimal]]:
        """(unit, hours) pairs, largest first, for the work-unit chart."""
        return sorted(zip(self.units, self.unit_totals, strict=True), key=lambda p: -p[1])


def intern_unit_matrix(qs) -> Matrix:
    """Hours by intern x work unit (the Summary sheet's main table), plus per-intern KPIs."""
    cells = qs.order_by().values("intern_id", "work_unit__name").annotate(hours=_sum())
    per_intern = (
        qs.order_by()
        .values("intern_id", "intern__display_name", "intern__sort_order")
        .annotate(
            total=_sum(),
            tasks=Count("id"),
            backlog_hours=_sum(Q(is_backlog=True)),
            ai_hours=_sum(Q(ai_used=True)),
            ai_tasks=Count("id", filter=Q(ai_used=True)),
        )
        .order_by("intern__sort_order", "intern__display_name")
    )
    grid: dict[tuple[int, str], Decimal] = {}
    names: set[str] = set()
    for c in cells:
        name = c["work_unit__name"] or NO_UNIT
        names.add(name)
        grid[(c["intern_id"], name)] = c["hours"]
    units = _ordered_units(names)

    matrix = Matrix(units=units)
    for p in per_intern:
        matrix.rows.append(
            MatrixRow(
                intern_id=p["intern_id"],
                intern=p["intern__display_name"],
                cells=[grid.get((p["intern_id"], u), ZERO) for u in units],
                total=p["total"],
                tasks=p["tasks"],
                backlog_hours=p["backlog_hours"],
                ai_hours=p["ai_hours"],
                ai_tasks=p["ai_tasks"],
            )
        )
    matrix.unit_totals = [sum((r.cells[i] for r in matrix.rows), ZERO) for i in range(len(units))]
    matrix.grand_total = sum((r.total for r in matrix.rows), ZERO)
    return matrix
