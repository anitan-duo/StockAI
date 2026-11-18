"""Forecast task registry: three independent prediction tasks.

Each task has its own target definition, labels, eligibility rules, and
evaluation — sharing the feature library and training infrastructure is
explicit, never implicit. Thresholds scale ~sqrt(horizon) from the v1
±0.5% 1-day band (documented choice, frozen per task version).

- h1d: next eligible trading session, ±0.5%  (v1-h1d-0.5pct, production v1.0)
- h5d: next 5 eligible sessions,    ±1.5%  (v1-h5d-1.5pct, research only)
- h20d: next 20 eligible sessions, ±3.0%  (v1-h20d-3.0pct, research only)

Sessions are TRADING sessions (exchange calendars/holidays respected via
actually-persisted bars — never calendar-day arithmetic). A task's labels,
metrics, and eligibility must never be compared across tasks as if they
were the same forecast.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForecastTask:
    task_id: str  # h1d | h5d | h20d
    horizon_sessions: int
    up_threshold: float
    down_threshold: float
    target_version: str
    cost_band_pct: float  # round-trip cost band for HOLD/action correctness
    production: bool  # only h1d serves production predictions


TASKS: dict[str, ForecastTask] = {
    "h1d": ForecastTask(
        task_id="h1d", horizon_sessions=1,
        up_threshold=0.005, down_threshold=-0.005,
        target_version="v1-h1d-0.5pct", cost_band_pct=0.15, production=True,
    ),
    "h5d": ForecastTask(
        task_id="h5d", horizon_sessions=5,
        up_threshold=0.015, down_threshold=-0.015,
        target_version="v1-h5d-1.5pct", cost_band_pct=0.35, production=False,
    ),
    "h20d": ForecastTask(
        task_id="h20d", horizon_sessions=20,
        up_threshold=0.03, down_threshold=-0.03,
        target_version="v1-h20d-3.0pct", cost_band_pct=0.60, production=False,
    ),
}

HORIZON_TO_TASK = {"1d": "h1d", "5d": "h5d", "20d": "h20d"}


def get_task(task_id: str) -> ForecastTask:
    try:
        return TASKS[task_id]
    except KeyError:
        raise ValueError(f"Unknown forecast task: {task_id}") from None


def label_return(task: ForecastTask, ret: float) -> str:
    """Direction label for a realized horizon return (strict thresholds)."""
    if ret > task.up_threshold:
        return "up"
    if ret < task.down_threshold:
        return "down"
    return "neutral"


def judge_action(task: ForecastTask, action: str, ret: float) -> bool:
    """Pre-registered action-correctness rule (position context: long-only;
    SELL means exit/hold-cash, never initiate short — no short support exists).

    - BUY correct iff return exceeds the round-trip cost band.
    - SELL correct iff return is worse than the negative cost band.
    - HOLD correct iff |return| stays inside the cost band (doing nothing was
      right because no action would have cleared costs). HOLD is never
      correct-by-default: it must satisfy the band.
    """
    band = task.cost_band_pct / 100.0
    action = action.upper()
    if action == "BUY":
        return ret > band
    if action == "SELL":
        return ret < -band
    if action == "HOLD":
        return abs(ret) <= band
    raise ValueError(f"Unknown action: {action}")
