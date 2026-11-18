"""Market-context engine wiring: panel plumbing, loud mismatch, real effect."""

from datetime import datetime, timedelta, timezone

import pytest


class _Bar:
    def __init__(self, ts, close, i):
        self.timestamp = ts
        self.open = close * 0.999
        self.high = close * 1.002
        self.low = close * 0.998
        self.close = close
        self.volume = 1_000_000 + (i % 7) * 100_000 + (i % 13) * 10_000


def _bars(n=400, drift_phase=0):
    out = []
    px = 100.0 + drift_phase * 10.0
    for i in range(n):
        # Regime blocks cycling +1.2% / flat / -1.1% / flat (all 3 classes).
        phase = (i // 5) % 4
        step = 0.012 if phase == 0 else (-0.011 if phase == 2 else 0.001)
        px *= 1.0 + step
        out.append(_Bar(datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i), px, i))
    return out


def _panel(n_syms=16):
    return {f"S{s}": _bars(400, drift_phase=s) for s in range(n_syms)}


def test_context_requires_panel_and_symbol():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp, market_context=True,
        )
    with pytest.raises(ValueError):
        BacktestEngine.build_window_training_rows(
            bars, 380, max_train_rows=50, market_context=True,
        )


def test_context_appends_six_columns_and_yields_predictions():
    from services.backtesting.backtest_service import BacktestEngine
    from services.ml.market_context import FEATURE_NAMES

    panel = _panel()
    rows, labels, cols, _ = BacktestEngine.build_window_training_rows(
        panel["S0"], 380, max_train_rows=100, feature_subset="normalized",
        market_context=True, panel=panel, symbol="S0",
    )
    assert len(rows) > 0
    assert cols[-6:] == list(FEATURE_NAMES)
    preds, method = BacktestEngine.generate_causal_predictions(
        panel["S0"], panel["S0"][380].timestamp, panel["S0"][-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5, max_train_rows=100,
        calibration="none", feature_subset="normalized",
        market_context=True, panel=panel, symbol="S0",
    )
    assert method["market_context"] is True
    assert len(preds) > 0
    for p in preds:
        assert p.window_fit_date < p.prediction_timestamp


def test_context_changes_predictions_vs_baseline():
    # The context features must actually participate (different columns ->
    # different model). If outputs were ever identical, the wiring would be
    # dead code.
    from services.backtesting.backtest_service import BacktestEngine

    panel = _panel()
    kw = dict(
        retrain_every_n_eval=4, eval_step_bars=5, max_train_rows=100,
        calibration="none", feature_subset="normalized",
    )
    base, _ = BacktestEngine.generate_causal_predictions(
        panel["S1"], panel["S1"][380].timestamp, panel["S1"][-1].timestamp, **kw,
    )
    ctx, _ = BacktestEngine.generate_causal_predictions(
        panel["S1"], panel["S1"][380].timestamp, panel["S1"][-1].timestamp,
        market_context=True, panel=panel, symbol="S1", **kw,
    )
    assert len(base) > 0 and len(ctx) > 0
    b = [(float(p.up_probability), float(p.down_probability)) for p in base]
    c = [(float(p.up_probability), float(p.down_probability)) for p in ctx]
    assert b != c
