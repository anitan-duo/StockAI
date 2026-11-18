"""Temporal-cutoff boundaries: no future data in training windows."""

from tests.backtesting.test_causal_walkforward import _bars  # noqa: F401 (shared fixture)


def test_label_bars_strictly_precede_eval():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    eval_index = 320
    rows, labels, cols, label_bars = BacktestEngine.build_window_training_rows(bars, eval_index)
    assert rows and cols
    assert all(k < eval_index for k in label_bars)
    eval_ts = bars[eval_index].timestamp
    assert all(bars[k].timestamp < eval_ts for k in label_bars)


def test_future_bars_do_not_change_window():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    eval_index = 320
    base = BacktestEngine.build_window_training_rows(bars, eval_index)
    # Corrupt the future: eval bar and beyond get extreme values
    tampered = list(bars)
    for j in range(eval_index, len(tampered)):
        b = tampered[j]
        tampered[j] = type(b)(
            timestamp=b.timestamp, open=b.open * 10, high=b.high * 10,
            low=b.low * 10, close=b.close * 10, volume=b.volume,
        )
    tampered_rows = BacktestEngine.build_window_training_rows(tampered, eval_index)
    assert [list(r) for r in base[0]] == [list(r) for r in tampered_rows[0]]
    assert base[1] == tampered_rows[1]


def test_target_needs_resolved_next_bar():
    """A row whose label bar is at/after T must be excluded (spot-check k=i-1 boundary)."""
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    eval_index = 320
    _, _, _, label_bars = BacktestEngine.build_window_training_rows(bars, eval_index)
    assert max(label_bars) == eval_index - 1
