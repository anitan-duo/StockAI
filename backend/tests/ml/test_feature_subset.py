"""P5 feature-subset mechanics: restriction-only ablation cannot leak.

Unit tests on synthetic column lists and small causal-engine fixtures.
The subset removes columns AFTER full computation, identically at train and
eval time; unknown names fail loudly.
"""

import pytest

from services.ml import recipe


def test_full_is_passthrough():
    cols = ["sma_20", "rsi_14", "close_position"]
    assert recipe.apply_feature_subset(cols, "full") == cols


def test_normalized_drops_levels_keeps_dimensionless():
    cols = [
        "sma_20", "sma_200", "ema_12", "obv", "obv_ema_20",
        "dollar_volume", "avg_dollar_volume_20",
        "pct_from_sma_20", "return_1d", "rsi_14", "macd",
        "close_position", "rel_volume_20d",
    ]
    kept = recipe.apply_feature_subset(cols, "normalized")
    assert "sma_20" not in kept and "ema_12" not in kept
    assert "obv" not in kept and "obv_ema_20" not in kept
    assert "dollar_volume" not in kept and "avg_dollar_volume_20" not in kept
    for c in ("pct_from_sma_20", "return_1d", "rsi_14", "macd", "close_position", "rel_volume_20d"):
        assert c in kept


def test_unknown_subset_raises():
    with pytest.raises(ValueError):
        recipe.apply_feature_subset(["a"], "bogus")


def test_subset_names_advertised():
    assert set(recipe.FEATURE_SUBSET_NAMES) == {"full", "normalized"}


def _bars(n: int = 300, start: float = 100.0):
    from datetime import datetime, timedelta, timezone

    out = []
    px = start
    for i in range(n):
        # Deterministic 5-day regime blocks cycling +1.2% / flat (+0.1%) /
        # -1.1% / flat: labels span UP, NEUTRAL and DOWN so windows hold all
        # three classes (a two-class fixture makes predict_proba 2-wide and
        # the engine correctly refuses to score it).
        phase = (i // 5) % 4
        step = 0.012 if phase == 0 else (-0.011 if phase == 2 else 0.001)
        px *= 1.0 + step
        out.append(
            _Bar(
                datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                px,
                i,
            )
        )
    return out


class _Bar:
    def __init__(self, ts, close, i):
        self.timestamp = ts
        self.open = close * 0.999
        self.high = close * 1.002
        self.low = close * 0.998
        self.close = close
        # Deterministic varying volume (constant volume makes vol-price
        # correlation NaN and every row would fail closed — correctly).
        self.volume = 1_000_000 + (i % 7) * 100_000 + (i % 13) * 10_000


def test_engine_subset_consistent_train_vs_eval():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    end = bars[-1].timestamp
    start = bars[380].timestamp
    preds, method = BacktestEngine.generate_causal_predictions(
        bars, start, end, retrain_every_n_eval=4, eval_step_bars=5,
        max_train_rows=100, calibration="none", feature_subset="normalized",
    )
    assert method["feature_subset"] == "normalized"
    # Non-vacuous: the fixture must actually yield predictions.
    assert len(preds) > 0
    # Methodology records the subset; predictions still well-formed.
    for p in preds:
        assert p.window_fit_date < p.prediction_timestamp
        assert float(p.up_probability) + float(p.neutral_probability) + float(p.down_probability) == pytest.approx(1.0, abs=1e-4)


def test_engine_unknown_subset_raises():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp, feature_subset="bogus",
        )


def test_subset_restricts_columns_not_rows():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(320)
    rows_full, _, cols_full, _ = BacktestEngine.build_window_training_rows(
        bars, 310, max_train_rows=50, feature_subset="full",
    )
    rows_sub, _, cols_sub, _ = BacktestEngine.build_window_training_rows(
        bars, 310, max_train_rows=50, feature_subset="normalized",
    )
    # Same rows (restriction removes columns only), strictly fewer columns.
    assert len(rows_full) == len(rows_sub) > 0
    assert len(cols_sub) < len(cols_full)
    assert set(cols_sub) < set(cols_full)
