"""Burned-range guard: experiment code must refuse burned periods.

This module blocks any code from using the sealed v1_holdout window for
selection, tuning, or optimization. It is deliberately enforced at the
filesystem/logic level so that no uncommitted script can silently read
holdout data and produce biased results.

BURNED_RANGES are the v1 holdout window and a prior phase-3 holdout window.
Code that needs to evaluate on a fresh holdout must use a window strictly
outside these ranges, or run in an authorized research pipeline that
documentedly operates on pre-approved slices.

The guard is a hard boundary: overlapping these ranges with any purpose
other than authorized evaluation reporting raises ValueError.
"""

from datetime import UTC, datetime

# (start, end, reason) — NEVER use for selection/tuning/optimization.
# The v1 holdout window is sealed and must never be used for model selection.
BURNED_RANGES: list[tuple[datetime, datetime, str]] = [
    (datetime(2026, 4, 1, tzinfo=UTC), datetime(2026, 8, 21, tzinfo=UTC), "v1-holdout"),
    (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC), "phase3-holdout-2"),
]


def assert_not_burned(start: datetime, end: datetime, purpose: str) -> None:
    """Raise if [start, end] overlaps any burned range (selection use only).

    Pure causal *evaluation reporting* on a fresh holdout is not selection;
    anything that influences features/models/thresholds/gates is.

    This is a hard boundary: any code path that enters a burned range for
    selection/tuning/optimization must be rejected.  The only permitted use
    is authorized evaluation reporting that documents the overlap and
    documents why it does not compromise the holdout integrity.
    """
    for bstart, bend, reason in BURNED_RANGES:
        if start <= bend and end >= bstart:
            raise ValueError(
                f"Refusing {purpose}: [{start.date()}, {end.date()}] overlaps burned {reason} "
                f"[{bstart.date()}, {bend.date()}]. See docs/research/V1_BASELINE.md."
            )