"""RSI correctness and point-in-time safety tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.ml.rsi_features import (
    detect_divergence,
    rsi_feature_frame,
    wilder_rsi,
)
from services.prediction.rsi_service import analyze_rsi_bars


def _close(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))


def test_rsi_bounds_and_extremes():
    up = wilder_rsi(_close(list(np.arange(1, 80, dtype=float))), 14)
    down = wilder_rsi(_close(list(np.arange(80, 1, -1, dtype=float))), 14)
    flat = wilder_rsi(_close([50.0] * 80), 14)
    assert up.iloc[-1] == pytest.approx(100.0)
    assert down.iloc[-1] == pytest.approx(0.0)
    assert flat.iloc[-1] == pytest.approx(50.0)
    valid = up.dropna()
    assert ((valid >= 0) & (valid <= 100)).all()


def test_rsi_is_causal_no_future_information():
    values = list(np.cumsum(np.sin(np.arange(200)) * 0.4 + 0.05) + 100)
    full = wilder_rsi(_close(values), 14)
    cut = 120
    partial = wilder_rsi(_close(values[:cut]), 14)
    assert full.iloc[:cut].equals(partial)


def test_rsi_feature_frame_only_uses_past_bars():
    n = 160
    close = 100 + np.cumsum(np.random.RandomState(7).randn(n) * 0.5)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1_000_000,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )
    full = rsi_feature_frame(frame)
    cut = 120
    partial = rsi_feature_frame(frame.iloc[:cut])
    common = [c for c in full.columns if c in partial.columns]
    pd.testing.assert_frame_equal(
        full.iloc[:cut][common].fillna(-999),
        partial[common].fillna(-999),
    )
    for col in ("rsi_wilder_7", "rsi_wilder_14", "rsi_wilder_21"):
        assert full[col].iloc[-1] == pytest.approx(
            wilder_rsi(frame["close"], int(col.rsplit("_", 1)[-1])).iloc[-1]
        )


def test_divergence_detection_is_deterministic_and_disclosed():
    close = _close(list(10 + np.cumsum(np.random.RandomState(11).randn(80) * 0.1)))
    rsi = wilder_rsi(close, 14)
    first = detect_divergence(close, rsi)
    second = detect_divergence(close, rsi)
    assert first == second
    assert first["kind"] in {"bullish", "bearish", "none"}
    assert "method" in first and "reason" in first


def test_analyze_rsi_bars_contract():
    n = 140
    close = 100 + np.cumsum(np.random.RandomState(3).randn(n) * 0.6)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": 1_000_000,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )
    out = analyze_rsi_bars(frame, prediction_direction="up")
    assert out["bar_count"] == n
    assert out["thresholds"] == {"overbought": 70, "oversold": 30}
    assert len(out["series"]) == 120
    for period in (7, 14, 21):
        value = out["current"][f"rsi_{period}"]
        assert 0 <= value <= 100
    assert out["agreement"]["status"] in {"agrees", "disagrees", "unknown"}
    assert out["zone"] in {"overbought", "oversold", "neutral"}
    assert out["trend"] in {"rising", "falling", "flat"}
    assert out["series"][-1]["timestamp"] == frame.index[-1].isoformat()


def test_analyze_requires_minimum_history():
    frame = pd.DataFrame(
        {"close": np.arange(20, dtype=float) + 10},
        index=pd.date_range("2024-01-01", periods=20, freq="D"),
    )
    with pytest.raises(ValueError, match="Insufficient history"):
        analyze_rsi_bars(frame)
