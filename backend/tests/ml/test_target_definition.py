"""Target audit: v1-h1d-0.5pct definition is exact and temporally sound.

Isolated unit tests on synthetic series (fixtures only — never research data).
Locks: thresholds, boundary inclusivity, NaN last bar, and the core invariant
that a feature timestamp strictly precedes its label's outcome timestamp.
"""

import numpy as np
import pandas as pd

from services.ml.target import TargetDefinition, TargetDirection, compute_target_series


def _closes(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def test_thresholds_match_recipe():
    from services.ml import recipe

    d = TargetDefinition()
    assert d.up_threshold == recipe.TARGET_UP_THRESHOLD == 0.005
    assert d.down_threshold == recipe.TARGET_DOWN_THRESHOLD == -0.005
    assert d.horizon_days == recipe.TARGET_HORIZON_DAYS == 1


def test_boundary_is_neutral_on_exact_threshold():
    d = TargetDefinition()
    # Strict > / <: exactly ±0.5% is NEUTRAL (documented target semantics).
    assert d.compute_target(100.0, 100.5) == TargetDirection.NEUTRAL
    assert d.compute_target(100.0, 99.5) == TargetDirection.NEUTRAL
    assert d.compute_target(100.0, 100.51) == TargetDirection.UP
    assert d.compute_target(100.0, 99.49) == TargetDirection.DOWN


def test_last_bar_has_no_label():
    s = _closes([100.0, 101.0, 102.0, 103.0])
    out = compute_target_series(s, TargetDefinition())
    assert len(out) == 4
    assert pd.isna(out.iloc[-1])
    assert not pd.isna(out.iloc[-2])


def test_label_uses_only_next_bar():
    # Flat then a jump: only the bar BEFORE the jump is UP.
    s = _closes([100.0, 100.0, 100.0, 102.0, 102.0])
    out = compute_target_series(s, TargetDefinition())
    assert out.iloc[1] == TargetDirection.NEUTRAL
    assert out.iloc[2] == TargetDirection.UP
    assert out.iloc[3] == TargetDirection.NEUTRAL


def test_feature_timestamp_precedes_outcome():
    # The label at feature-time t resolves on close t+1: shifting the label
    # back by one must recover the next-bar return exactly (no lookahead).
    closes = _closes([100.0, 101.0, 99.0, 100.5, 98.0])
    out = compute_target_series(closes, TargetDefinition())
    for i in range(len(closes) - 1):
        ret = (closes.iloc[i + 1] - closes.iloc[i]) / closes.iloc[i]
        expected = (
            TargetDirection.UP
            if ret > 0.005
            else TargetDirection.DOWN
            if ret < -0.005
            else TargetDirection.NEUTRAL
        )
        assert out.iloc[i] == expected
        assert out.index[i] < out.index[i + 1]


def test_zero_base_close_is_neutral_not_crash():
    d = TargetDefinition()
    assert d.compute_target(0.0, 100.0) == TargetDirection.NEUTRAL
