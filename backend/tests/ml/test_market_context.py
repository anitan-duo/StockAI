"""Cross-sectional context: causal, hand-checkable, future-invariant."""

from datetime import datetime, timedelta, timezone

import pytest

from services.ml.market_context import FEATURE_NAMES, cross_sectional_context


def _panel(n_syms=16, n_days=70, start_px=100.0, drift=0.001):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    panel = {}
    for s in range(n_syms):
        series = []
        px = start_px + s
        for i in range(n_days):
            px *= 1.0 + drift + (0.0005 if (i + s) % 2 else -0.0005)
            series.append((base + timedelta(days=i), px))
        panel[f"S{s}"] = series
    return panel


def test_feature_names_stable():
    assert FEATURE_NAMES == (
        "xs_excess_ret_20d",
        "xs_rel_strength_60d",
        "xs_rank_20d",
        "xs_dispersion_20d",
        "xs_mkt_vol_20d",
        "xs_breadth_60d",
    )


def test_values_bounded_and_signed_correctly():
    panel = _panel()
    asof = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=69)
    out = cross_sectional_context(panel, "S0", asof)
    assert out is not None
    assert 0.0 <= out["xs_rank_20d"] <= 1.0
    assert 0.0 <= out["xs_breadth_60d"] <= 1.0
    assert out["xs_dispersion_20d"] >= 0.0
    assert out["xs_mkt_vol_20d"] >= 0.0


def test_future_panel_bars_cannot_change_row():
    panel = _panel()
    asof = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=65)
    before = cross_sectional_context(panel, "S3", asof)
    # Append extreme future bars (10x spike) AFTER asof to every symbol.
    for sym, series in panel.items():
        last_ts, last_px = series[-1]
        series.append((last_ts + timedelta(days=1), last_px * 10.0))
    after = cross_sectional_context(panel, "S3", asof)
    assert before == after


def test_insufficient_panel_fails_closed():
    assert cross_sectional_context(_panel(n_syms=5), "S0", datetime(2024, 3, 1, tzinfo=timezone.utc)) is None
    assert cross_sectional_context(_panel(), "NOPE", datetime(2024, 3, 1, tzinfo=timezone.utc)) is None
    # asof before enough history exists
    assert cross_sectional_context(_panel(), "S0", datetime(2024, 1, 5, tzinfo=timezone.utc)) is None


def test_rank_top_symbol_is_one():
    # S0 drifts up fastest -> rank 1.0 (all others below).
    panel = _panel(drift=0.0)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    series = []
    px = 50.0
    for i in range(70):
        px *= 1.05
        series.append((base + timedelta(days=i), px))
    panel["ROCKET"] = series
    out = cross_sectional_context(panel, "ROCKET", base + timedelta(days=69))
    assert out is not None
    # Rank = fraction strictly below: the top of 17 symbols scores 16/17.
    assert out["xs_rank_20d"] == pytest.approx(16 / 17)
    assert out["xs_excess_ret_20d"] > 0
