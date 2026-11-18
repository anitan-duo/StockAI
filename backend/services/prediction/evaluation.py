"""Canonical prediction-evaluation engine — the single source of truth.

Every hit rate, accuracy figure, coverage number, and confidence interval
shown anywhere in StockAI (API, analytics workspace, monitor, stock page,
research reports) MUST be derived from this module. There is exactly one
definition of "correct", one denominator policy, and one pending/invalid
policy:

Scoring policy
--------------
* A prediction is **evaluated** only when a persisted outcome exists and its
  actual direction is one of ``up`` / ``neutral`` / ``down``.
* Predictions without an outcome are **pending**. They are never counted as
  incorrect and never enter any denominator described below.
* Predictions with an unusable/invalid direction or outcome are **invalid**
  and reported separately.
* **Directional accuracy** (the headline hit rate) is::

      directional_correct / directional_evaluated

  where ``directional_evaluated`` counts only predictions whose *predicted*
  direction is UP or DOWN and which are evaluated. A directional prediction
  is correct iff the realised direction equals it exactly; a realised
  ``neutral`` therefore makes a directional call incorrect.
* **Neutral predictions** are excluded from directional accuracy and reported
  separately as ``neutral_correct / neutral_evaluated``. Counting
  neutral-vs-neutral as a directional win is prohibited — doing so lets a
  model inflate hit rate by predicting ``neutral`` on most days.
* **3-class accuracy** (``all_class_accuracy``) counts exact class matches
  including neutral-vs-neutral. It is a diagnostic for calibration, never the
  advertised "hit rate".
* Accuracy is reported as a fraction in ``[0, 1]`` here; API layers that
  historically used percentages multiply exactly once at their boundary.
* Samples below ``MIN_SAMPLE`` are flagged ``reliable = False``; the number is
  still reported but must be labelled as unreliable, never silently shown as a
  trustworthy hit rate.
* The 95% confidence interval is the Wilson score interval, which behaves
  correctly for small n and proportions near 0 or 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

MIN_SAMPLE = 30
CONFIDENCE_LEVEL = 0.95
SCORING_POLICY = (
    "Directional accuracy = correct UP/DOWN calls / evaluated UP/DOWN calls. "
    "Neutral predictions are reported separately and never counted as "
    "directional wins. Pending predictions are excluded, never treated as "
    "incorrect. Exact 3-class accuracy is diagnostic only."
)

_VALID_DIRECTIONS = {"up", "neutral", "down"}


def normalize_direction(value: Any) -> str | None:
    """Return the canonical lower-case direction string, or None if invalid."""
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip().lower()
    return text if text in _VALID_DIRECTIONS else None


@dataclass(frozen=True)
class Record:
    """A single prediction/outcome pair in canonical form."""

    predicted: str | None
    actual: str | None
    status: str = "evaluated"
    actual_return: float | None = None
    evaluated_at: datetime | None = None

    @property
    def evaluated(self) -> bool:
        return (
            self.status == "evaluated"
            and self.predicted in _VALID_DIRECTIONS
            and self.actual in _VALID_DIRECTIONS
        )

    @property
    def directional(self) -> bool:
        return self.evaluated and self.predicted in {"up", "down"}

    @property
    def directional_correct(self) -> bool:
        return self.directional and self.predicted == self.actual

    @property
    def neutral(self) -> bool:
        return self.evaluated and self.predicted == "neutral"

    @property
    def neutral_correct(self) -> bool:
        return self.neutral and self.actual == "neutral"

    @property
    def class_correct(self) -> bool:
        return self.evaluated and self.predicted == self.actual


def make_record(
    predicted: Any,
    actual: Any,
    *,
    status: str | None = None,
    actual_return: Any = None,
    evaluated_at: datetime | None = None,
) -> Record:
    """Build a canonical record from raw persisted values."""
    pred = normalize_direction(predicted)
    act = normalize_direction(actual)
    if status is None:
        status = "evaluated" if act is not None else "pending"
    if status == "evaluated" and (pred is None or act is None):
        status = "invalid"
    ret: float | None
    try:
        ret = None if actual_return is None else float(actual_return)
    except (TypeError, ValueError):
        ret = None
    return Record(
        predicted=pred,
        actual=act,
        status=status,
        actual_return=ret,
        evaluated_at=evaluated_at,
    )


def record_from_prediction(prediction: Any, outcome: Any | None = None, *, status: str | None = None) -> Record:
    """Canonical record from ORM ``Prediction`` (+ optional outcome).

    Deliberately ignores the stored ``PredictionOutcome.is_correct`` flag:
    historical rows were written with 3-class equality, which is not the
    canonical directional definition. Correctness is always recomputed.
    """
    predicted = getattr(prediction, "predicted_direction", None)
    actual = getattr(outcome, "actual_direction", None) if outcome is not None else None
    actual_return = getattr(outcome, "actual_return", None) if outcome is not None else None
    if status is None:
        status = "evaluated" if outcome is not None else "pending"
    evaluated_at = getattr(outcome, "evaluated_at", None) if outcome is not None else None
    return make_record(
        predicted,
        actual,
        status=status,
        actual_return=actual_return,
        evaluated_at=evaluated_at,
    )


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - margin), min(1.0, centre + margin)


def score_records(
    records: Iterable[Record | Mapping[str, Any]],
    *,
    min_sample: int = MIN_SAMPLE,
    confidence_level: float = CONFIDENCE_LEVEL,
) -> dict:
    """Score canonical records. All counts are explicit and mutually exclusive."""
    recs: list[Record] = []
    for item in records:
        if isinstance(item, Record):
            recs.append(item)
        else:
            recs.append(
                make_record(
                    item.get("predicted"),
                    item.get("actual"),
                    status=item.get("status"),
                    actual_return=item.get("actual_return"),
                    evaluated_at=item.get("evaluated_at"),
                )
            )

    total = len(recs)
    evaluated = [r for r in recs if r.evaluated]
    directional = [r for r in evaluated if r.directional]
    neutral = [r for r in evaluated if r.neutral]
    pending = [r for r in recs if r.status == "pending" and not r.evaluated]
    invalid = [r for r in recs if r.status == "invalid"]
    expired = [r for r in recs if r.status == "expired"]

    dir_n = len(directional)
    dir_correct = sum(1 for r in directional if r.directional_correct)
    neutral_correct = sum(1 for r in neutral if r.neutral_correct)
    all_correct = dir_correct + neutral_correct
    eval_n = len(evaluated)

    accuracy = (dir_correct / dir_n) if dir_n else None
    all_class_accuracy = (all_correct / eval_n) if eval_n else None
    ci = wilson_interval(dir_correct, dir_n) if dir_n else None

    returns = [r.actual_return for r in directional if r.actual_return is not None]
    eval_dates = [r.evaluated_at for r in evaluated if r.evaluated_at is not None]

    return {
        # volume / lifecycle
        "n": total,
        "evaluated": eval_n,
        "pending": len(pending),
        "invalid": len(invalid),
        "expired": len(expired),
        # headline directional score
        "directional_n": dir_n,
        "directional_correct": dir_correct,
        "directional_incorrect": dir_n - dir_correct,
        "accuracy": None if accuracy is None else round(accuracy, 6),
        "confidence_interval": (
            None
            if ci is None
            else {
                "lower": round(ci[0], 6),
                "upper": round(ci[1], 6),
                "level": confidence_level,
            }
        ),
        # neutral class reported separately (never in headline)
        "neutral_n": len(neutral),
        "neutral_correct": neutral_correct,
        "neutral_accuracy": (
            None if not neutral else round(neutral_correct / len(neutral), 6)
        ),
        # diagnostic 3-class score
        "all_class_correct": all_correct,
        "all_class_accuracy": (
            None if all_class_accuracy is None else round(all_class_accuracy, 6)
        ),
        # coverage over the full scoped set
        "coverage": (eval_n / total) if total else None,
        "directional_coverage": (dir_n / total) if total else None,
        # honesty flags
        "reliable": dir_n >= min_sample,
        "minimum_sample": min_sample,
        "average_return": (
            round(sum(returns) / len(returns), 6) if returns else None
        ),
        "evaluation_period": {
            "start": min(eval_dates).isoformat() if eval_dates else None,
            "end": max(eval_dates).isoformat() if eval_dates else None,
        },
        "scoring_policy": SCORING_POLICY,
    }


def metric_cell(records: Iterable[Record | Mapping[str, Any]], *, min_sample: int = MIN_SAMPLE) -> dict:
    """Compact score used for grouped tables (symbol/market/version/regime).

    Keeps the historical ``accuracy``/``reliable`` keys while exposing the
    canonical counts so a UI can explain the denominator.
    """
    summary = score_records(records, min_sample=min_sample)
    summary.pop("scoring_policy", None)
    return summary
