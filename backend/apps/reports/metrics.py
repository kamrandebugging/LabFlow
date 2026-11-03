"""TAT (turnaround time) metrics — pure functions over plain data
(Doc 03 §11.2; KAN-157 / LAB-32, original LAB-41).

Design rules:
- Every function here operates on plain Python data (datetimes, lists,
  dicts) — no Django models, no DB. All of it is unit-testable without a
  database. The DB-touching wrapper is `compute_tat_metrics` in
  apps/reports/services.py.
- TAT_DEFINITION is printed next to every TAT figure (§11.2: LabFlow states
  its definition instead of pretending there is one true number).
- Exclusions (§11.2): rejected and cancelled samples are excluded from TAT
  and counted separately. Recollected samples are measured from the
  *replacement* sample's collection — each sample is measured
  independently; v1 has no cross-sample linkage, so the patient-journey
  second figure (§11.2) is documented but NOT implemented.
- Samples still in flight (no finalised_at) are not in TAT at all.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# §11.2: stated wherever TAT is shown.
TAT_DEFINITION = (
    "sample TAT = report.finalised_at − sample.collected_at "
    "for samples that reached a final report (Doc 03 §11.2)."
)

# Stage boundaries in event order. The last leg (READY -> finalised) uses
# report.finalised_at, not a sample_event row.
_STAGE_SEQUENCE = ("COLLECTED", "RECEIVED", "IN_PROCESS", "READY", "FINALIZED")
STAGE_LABELS = {
    ("COLLECTED", "RECEIVED"): "collection_to_receipt",
    ("RECEIVED", "IN_PROCESS"): "receipt_to_in_process",
    ("IN_PROCESS", "READY"): "in_process_to_ready",
    ("READY", "FINALIZED"): "ready_to_finalised",
}

EXCLUDED_STATUSES = ("rejected", "cancelled")


def stage_durations_seconds(
    collected_at: datetime | None,
    events: list[tuple[str, datetime]],
    finalised_at: datetime | None,
) -> dict[str, float | None]:
    """Split one sample's journey into the four §11.2 stage durations.

    Uses the FIRST timestamp seen per stage (a stage recorded twice keeps
    the earliest). A stage with no recorded timestamp yields None for its
    duration instead of corrupting the others.
    """
    first: dict[str, datetime] = {}
    for event_type, ts in sorted(events, key=lambda e: e[1]):
        first.setdefault(event_type, ts)
    if collected_at is not None:
        first.setdefault("COLLECTED", collected_at)
    times: dict[str, datetime | None] = {**first, "FINALIZED": finalised_at}
    out: dict[str, float | None] = {}
    for start, end in zip(_STAGE_SEQUENCE, _STAGE_SEQUENCE[1:], strict=False):
        label = STAGE_LABELS[(start, end)]
        t0, t1 = times.get(start), times.get(end)
        if t0 is None or t1 is None:
            out[label] = None
        else:
            out[label] = (t1 - t0).total_seconds()
    return out


def tat_seconds(
    collected_at: datetime | None, finalised_at: datetime | None
) -> float | None:
    """The §11.2 definition, or None when the sample never finalised."""
    if collected_at is None or finalised_at is None:
        return None
    return (finalised_at - collected_at).total_seconds()


def median_seconds(values: list[float]) -> float | None:
    """Median of a duration list in seconds; None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile_seconds(values: list[float], pct: float) -> float | None:
    """pth percentile via linear interpolation (numpy 'linear' method)."""
    if not values:
        return None
    if not 0 <= pct <= 100:
        raise ValueError("pct must be in [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    frac = rank - low
    return ordered[low] + frac * (ordered[low + 1] - ordered[low])


def aggregate_tat(rows: list[dict[str, object]]) -> dict[str, Any]:
    """Aggregate per-sample rows into per-branch-per-week TAT figures.

    Each row: {"branch_id": str, "week": (iso_year, iso_week),
    "collected_at": datetime, "finalised_at": datetime | None,
    "events": [(event_type, datetime)], "status": str}.

    Returns {"definition": TAT_DEFINITION,
    "per_branch_week": {branch_id: {(y, w): {"count", "tat_median_seconds",
    "tat_p90_seconds", "stages": {stage: {"median_seconds",
    "p90_seconds"}}}}}, "excluded": {"rejected": n, "cancelled": n}}.
    """
    groups: dict[str, dict[tuple[int, int], list[dict[str, object]]]] = {}
    excluded = {"rejected": 0, "cancelled": 0}
    for row in rows:
        status = str(row.get("status", ""))
        if status in EXCLUDED_STATUSES:
            excluded[status] += 1
            continue
        collected = row.get("collected_at")
        finalised = row.get("finalised_at")
        tat = (
            tat_seconds(collected, finalised)
            if isinstance(collected, datetime) and isinstance(finalised, datetime)
            else None
        )
        if tat is None:
            # In flight: not in TAT at all (§11.2) — and not an exclusion.
            continue
        branch_id = str(row["branch_id"])
        week = row["week"]
        assert isinstance(week, tuple) and len(week) == 2
        groups.setdefault(branch_id, {}).setdefault(week, []).append(row)

    per_branch_week: dict[str, dict[tuple[int, int], dict[str, object]]] = {}
    for branch_id, weeks in groups.items():
        per_branch_week[branch_id] = {}
        for week, members in weeks.items():
            tats: list[float] = []
            stage_vals: dict[str, list[float]] = {
                label: [] for label in STAGE_LABELS.values()
            }
            for m in members:
                collected = m["collected_at"]
                finalised = m["finalised_at"]
                assert isinstance(collected, datetime)
                assert isinstance(finalised, datetime)
                events = m.get("events", [])
                assert isinstance(events, list)
                t = tat_seconds(collected, finalised)
                assert t is not None
                tats.append(t)
                for stage, secs in stage_durations_seconds(
                    collected, events, finalised
                ).items():
                    if secs is not None:
                        stage_vals[stage].append(secs)
            per_branch_week[branch_id][week] = {
                "count": len(members),
                "tat_median_seconds": median_seconds(tats),
                "tat_p90_seconds": percentile_seconds(tats, 90),
                "stages": {
                    stage: {
                        "median_seconds": median_seconds(vals),
                        "p90_seconds": percentile_seconds(vals, 90),
                    }
                    for stage, vals in stage_vals.items()
                },
            }
    return {
        "definition": TAT_DEFINITION,
        "per_branch_week": per_branch_week,
        "excluded": excluded,
    }
