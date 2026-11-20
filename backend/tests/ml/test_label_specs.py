"""P7 label specs: binary exclusion, 5d windows, v1 parity, loud unknowns."""

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


def _bars(n=400):
    out = []
    px = 100.0
    for i in range(n):
        phase = (i // 5) % 4
        step = 0.012 if phase == 0 else (-0.011 if phase == 2 else 0.001)
        px *= 1.0 + step
        out.append(_Bar(datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i), px, i))
    return out


def test_unknown_label_spec_raises_everywhere():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    with pytest.raises(ValueError):
        BacktestEngine.build_window_training_rows(bars, 380, max_train_rows=50, label_spec="bogus")
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp, label_spec="bogus",
        )


def test_direction3_1d_reproduces_v1_labels_exactly():
    """Default and explicit specs must be bit-identical (no silent drift)."""
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    r1, l1, _, _ = BacktestEngine.build_window_training_rows(bars, 380, max_train_rows=50)
    r2, l2, _, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, label_spec="direction3-1d")
    assert l1 == l2
    assert set(l1) <= {0, 1, 2}


def test_binary_drops_neutral_keeps_direction():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    rows, labels, cols, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, label_spec="binary-1d")
    assert set(labels) <= {0, 1}
    # Fewer rows than 3-class (neutral zone excluded, documented).
    _, labels3, _, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, label_spec="direction3-1d")
    assert len(labels) < len(labels3)
    assert len(labels) > 0


def test_5d_labels_need_future_window_end():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    rows, labels, cols, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, label_spec="direction3-5d")
    assert set(labels) <= {0, 1, 2}
    assert len(labels) > 0


def _load_runner():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "run_holdout_evaluation.py"
    if not path.exists():
        pytest.skip("Private holdout evaluation runner is not distributed in the public repository")
    spec = importlib.util.spec_from_file_location("run_holdout_evaluation", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_1pct_band_boundaries_agree_train_and_eval():
    """P10: ±1.0% train labels and eval mapping must use the same thresholds."""
    from services.backtesting.backtest_service import BacktestEngine
    from services.ml.recipe import TARGET_WIDE_DOWN_THRESHOLD, TARGET_WIDE_UP_THRESHOLD

    assert (TARGET_WIDE_UP_THRESHOLD, TARGET_WIDE_DOWN_THRESHOLD) == (0.01, -0.01)
    bars = _bars()
    _, labels, _, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, label_spec="direction3-1d-1pct")
    assert set(labels) <= {0, 1, 2}
    assert len(labels) > 0
    # Train mapping (_label_for_row) and eval mapping (runner _label_1pct)
    # must classify identically at the boundaries.
    runner = _load_runner()

    assert runner.TARGET_SPECS["direction3-1d-1pct"][0] == 1  # 1-bar offset
    assert runner.TARGET_SPECS["direction3-1d-1pct"][2:] == ([0, 1, 2], True)
    for ret, want in ((0.0101, 2), (0.01, 1), (0.0, 1), (-0.01, 1), (-0.0101, 0)):
        assert runner._label_1pct(ret) == want
    closes = [100.0, 100.0, 100.0 * 1.0101, 100.0 * 0.9899]
    assert BacktestEngine._label_for_row("direction3-1d-1pct", closes, 2, 4) == 2
    assert BacktestEngine._label_for_row("direction3-1d-1pct", closes, 3, 4) == 0
