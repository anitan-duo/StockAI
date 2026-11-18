"""Tests for P18-E022 earnings features + engine opt-in (always-present path)."""

from datetime import UTC, date, datetime

from services.ml.earnings import CAP_DAYS, FEATURE_NAMES, build_entries, lookup


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def test_feature_names_and_sentinel_before_first_event():
    entries = build_entries([{"symbol": "AAPL", "announce_date": "2024-02-01",
                              "surprise_pct": "4.2"}])
    f = lookup(entries, _dt("2023-12-31"))
    assert set(f) == set(FEATURE_NAMES)
    assert f["earn_days_since"] == CAP_DAYS
    assert f["earn_last_surprise"] == 0.0
    assert f["earn_in_window"] == 0.0
    assert f["earn_surprise_recent"] == 0.0


def test_pit_gate_no_future_leak():
    entries = build_entries([{"symbol": "AAPL", "announce_date": "2024-02-01",
                              "surprise_pct": "4.2"}])
    before = lookup(entries, _dt("2024-01-31"))
    on = lookup(entries, _dt("2024-02-01"))
    assert before["earn_last_surprise"] == 0.0
    assert on["earn_last_surprise"] == 4.2
    assert on["earn_in_window"] == 1.0
    assert on["earn_surprise_recent"] == 4.2
    assert on["earn_days_since"] == 0.0


def test_window_decay_and_recency():
    entries = build_entries([
        {"symbol": "X", "announce_date": "2024-02-01", "surprise_pct": "4.2"},
        {"symbol": "X", "announce_date": "2024-05-01", "surprise_pct": "-3.0"},
    ])
    f = lookup(entries, _dt("2024-05-07"))
    assert f["earn_days_since"] == 6.0
    assert f["earn_in_window"] == 0.0
    assert f["earn_last_surprise"] == -3.0
    assert f["earn_surprise_recent"] == 0.0
    g = lookup(entries, _dt("2024-05-03"))
    assert g["earn_in_window"] == 1.0
    assert g["earn_surprise_recent"] == -3.0


def test_clip_and_cap():
    entries = build_entries([{"symbol": "X", "announce_date": "2010-01-01",
                              "surprise_pct": "999"}])
    f = lookup(entries, _dt("2025-01-01"))
    assert f["earn_days_since"] == CAP_DAYS
    assert f["earn_last_surprise"] == 50.0


def test_build_entries_skips_bad_dates_sorts():
    rows = [{"symbol": "X", "announce_date": "bad", "surprise_pct": "1"},
            {"symbol": "X", "announce_date": "2024-05-01", "surprise_pct": ""},
            {"symbol": "X", "announce_date": "2024-02-01", "surprise_pct": "2"}]
    e = build_entries(rows)
    assert [d for d, _ in e] == [date(2024, 2, 1), date(2024, 5, 1)]
    assert e[0][1] == 2.0 and e[1][1] is None


def test_engine_earnings_arm_is_always_present_and_isolated():
    """build_window_training_rows with earnings= adds columns, drops no rows."""
    from datetime import timedelta

    from services.backtesting.backtest_service import BacktestEngine
    from services.ml.earnings import FEATURE_NAMES as EARN

    class Bar:
        def __init__(self, ts, c, v):
            self.timestamp = ts
            self.open = c
            self.high = c * 1.01
            self.low = c * 0.99
            self.close = c
            self.volume = v

    start = datetime(2023, 1, 2, tzinfo=UTC)
    px = []
    x = 100.0
    for i in range(320):
        x = x * (1.0 + (((i * 2654435761) % 101) - 50) / 5000.0)
        px.append(x)
    bars = [Bar(start + timedelta(days=i), px[i], 1000.0 + (i * 97) % 500) for i in range(320)]
    engine = BacktestEngine.__new__(BacktestEngine)
    base = BacktestEngine.build_window_training_rows(
        bars, 300, max_train_rows=40, label_spec="direction3-1d")
    ear = BacktestEngine.build_window_training_rows(
        bars, 300, max_train_rows=40, label_spec="direction3-1d",
        earnings=True, earnings_panel={"TEST": []}, symbol="TEST")
    assert len(base[1]) == len(ear[1])  # identical rows (no drop)
    assert ear[2][-len(EARN):] == list(EARN)
    assert len(ear[2]) == len(base[2]) + len(EARN)
    # sentinel before any event
    assert ear[0][0][-1] == 0.0
