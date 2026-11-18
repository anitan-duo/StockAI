"""Regression tests for the canonical evaluation engine.

These lock the hit-rate semantics: neutral predictions must never inflate the
headline directional accuracy, pending predictions are never incorrect, and
historical ``is_correct`` flags cannot override the canonical recomputation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.prediction.evaluation import (
    MIN_SAMPLE,
    make_record,
    record_from_prediction,
    score_records,
    wilson_interval,
)


def _recs(predicted, actual):
    return [make_record(p, a) for p, a in zip(predicted, actual, strict=True)]


def test_directional_accuracy_excludes_neutral_predictions():
    # 4 directional calls (3 right), 6 neutral calls (all "right" by class).
    records = _recs(
        ["up", "down", "up", "down", "neutral", "neutral", "neutral", "neutral", "neutral", "neutral"],
        ["up", "up", "up", "down", "neutral", "neutral", "neutral", "neutral", "neutral", "neutral"],
    )
    summary = score_records(records)
    assert summary["directional_n"] == 4
    assert summary["directional_correct"] == 3
    assert summary["directional_incorrect"] == 1
    assert summary["accuracy"] == pytest.approx(0.75)
    assert summary["neutral_n"] == 6
    assert summary["neutral_correct"] == 6
    assert summary["neutral_accuracy"] == pytest.approx(1.0)
    # Diagnostic 3-class accuracy is 9/10 and must NOT be the headline.
    assert summary["all_class_accuracy"] == pytest.approx(0.9)
    assert summary["accuracy"] != summary["all_class_accuracy"]


def test_neutral_only_strategy_cannot_claim_accuracy():
    records = _recs(["neutral"] * 100, ["neutral"] * 100)
    summary = score_records(records)
    assert summary["directional_n"] == 0
    assert summary["accuracy"] is None
    assert summary["neutral_accuracy"] == pytest.approx(1.0)
    assert summary["reliable"] is False


def test_realised_neutral_makes_directional_call_incorrect():
    summary = score_records(_recs(["up", "down"], ["neutral", "neutral"]))
    assert summary["directional_n"] == 2
    assert summary["directional_correct"] == 0
    assert summary["accuracy"] == pytest.approx(0.0)


def test_pending_predictions_are_excluded_not_wrong():
    records = [
        make_record("up", "up"),
        make_record("down", "down"),
        make_record("up", None),
        make_record("neutral", None),
    ]
    summary = score_records(records)
    assert summary["evaluated"] == 2
    assert summary["pending"] == 2
    assert summary["directional_n"] == 2
    assert summary["directional_correct"] == 2
    assert summary["accuracy"] == pytest.approx(1.0)
    assert summary["coverage"] == pytest.approx(0.5)


def test_invalid_and_expired_are_reported_separately():
    records = [
        make_record("up", "up"),
        make_record("sideways", "up", status="invalid"),
        make_record("up", None, status="expired"),
    ]
    summary = score_records(records)
    assert summary["n"] == 3
    assert summary["evaluated"] == 1
    assert summary["invalid"] == 1  # unusable predicted direction
    assert summary["expired"] == 1
    assert summary["directional_n"] == 1
    assert summary["accuracy"] == pytest.approx(1.0)


def test_small_sample_is_flagged_unreliable():
    summary = score_records(_recs(["up"] * 29, ["up"] * 29))
    assert summary["directional_n"] == 29
    assert summary["reliable"] is False
    assert summary["minimum_sample"] == MIN_SAMPLE

    summary = score_records(_recs(["up"] * 30, ["up"] * 30))
    assert summary["reliable"] is True


def test_wilson_interval_is_bounded_and_narrows_with_n():
    small = wilson_interval(8, 10)
    large = wilson_interval(800, 1000)
    assert small is not None and large is not None
    assert 0.0 <= small[0] <= small[1] <= 1.0
    assert 0.0 <= large[0] <= large[1] <= 1.0
    assert (large[1] - large[0]) < (small[1] - small[0])
    assert wilson_interval(0, 0) is None


def test_stored_is_correct_flag_is_ignored():
    # A legacy row claims "correct" for a neutral-vs-neutral prediction.
    pred = SimpleNamespace(predicted_direction="neutral")
    outcome = SimpleNamespace(
        actual_direction="neutral",
        actual_return=0,
        is_correct=True,
        evaluated_at=datetime.now(UTC),
    )
    record = record_from_prediction(pred, outcome)
    summary = score_records([record])
    assert summary["directional_n"] == 0
    assert summary["accuracy"] is None
    assert summary["neutral_correct"] == 1


def test_mixed_case_and_enum_like_values_normalize():
    class Dir:
        value = "UP"

    summary = score_records([make_record(Dir(), "up")])
    assert summary["directional_correct"] == 1


def test_duplicate_outcomes_cannot_be_counted_by_engine():
    # The engine scores rows; duplicate-row prevention is enforced at the
    # persistence layer (unique prediction_id). This test documents that
    # scoring does not silently de-duplicate: the caller must supply one row
    # per prediction.
    summary = score_records(_recs(["up", "up"], ["up", "up"]))
    assert summary["n"] == 2
