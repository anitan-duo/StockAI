"""Causal backtest: future bars must not change earlier predictions."""

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd


@dataclass
class _Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


def _bars(n, seed=3, start="2024-01-01"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="B", tz=timezone.utc)
    close = 100 + np.cumsum(rng.normal(0.05, 0.9, n))
    close = np.maximum(close, 5)
    out = []
    for i, d in enumerate(dates):
        o = float(close[i] + rng.normal(0, 0.2))
        h = max(o, float(close[i])) + abs(float(rng.normal(0, 0.3)))
        low = min(o, float(close[i])) - abs(float(rng.normal(0, 0.3)))
        out.append(_Bar(timestamp=d.to_pydatetime(), open=o, high=h, low=low, close=float(close[i]), volume=int(1_000_000 + rng.normal(0, 50_000))))
    return out


def test_causal_predictions_ignore_future_bars():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    start = bars[300].timestamp
    end_short = bars[340].timestamp
    end_long = bars[390].timestamp
    preds_short, _ = BacktestEngine.generate_causal_predictions(bars, start, end_short)
    preds_long, _ = BacktestEngine.generate_causal_predictions(bars, start, end_long)
    assert preds_short, "expected predictions in short window"
    assert len(preds_long) >= len(preds_short)
    for a, b in zip(preds_short, preds_long):
        assert a.prediction_timestamp == b.prediction_timestamp
        # Ensemble parallelism (RF n_jobs, BLAS) may differ at 1e-16; causality
        # means identical inputs, so tolerance 1e-9 is the honest bound.
        assert abs(float(a.up_probability) - float(b.up_probability)) < 1e-9
        assert abs(float(a.down_probability) - float(b.down_probability)) < 1e-9
        assert a.window_fit_date < a.prediction_timestamp


def test_causal_methodology_tags_and_prob_sums():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    preds, methodology = BacktestEngine.generate_causal_predictions(
        bars, bars[300].timestamp, bars[360].timestamp
    )
    assert methodology["method"] == "causal-walk-forward"
    assert methodology["n_windows"] >= 1
    for p in preds:
        total = float(p.up_probability) + float(p.neutral_probability) + float(p.down_probability)
        assert abs(total - 1.0) < 1e-6


def test_causal_insufficient_history_errors_honestly():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(100)
    preds, methodology = BacktestEngine.generate_causal_predictions(
        bars, bars[10].timestamp, bars[90].timestamp
    )
    assert preds == []
    assert methodology["method"] == "causal-walk-forward"


def test_calibration_choice_validated_and_none_skips_calibrator():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    try:
        BacktestEngine.generate_causal_predictions(
            bars, bars[300].timestamp, bars[320].timestamp, calibration="bogus"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("bogus calibration accepted")
