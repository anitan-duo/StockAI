"""Regression: inference feature frames must have one row per trading day.

Providers double-stamp days (00:00 + 04:00 UTC). Before the fix, the
inference OHLCV frame kept both rows, halving every rolling window
(SMA200 spanned ~100 distinct days) and distorting rel-volume features."""

from __future__ import annotations

import pandas as pd
import pytest

from services.prediction.prediction_service import deduplicate_trading_days


def _df(stamps):
    return pd.DataFrame(
        {
            "open": [100.0] * len(stamps),
            "high": [101.0] * len(stamps),
            "low": [99.0] * len(stamps),
            "close": [100.5] * len(stamps),
            "volume": [1000.0] * len(stamps),
        },
        index=pd.DatetimeIndex(stamps, name="timestamp"),
    )


def test_double_stamped_days_collapse_to_one_row():
    stamps = [
        "2026-11-04 00:00", "2026-11-04 04:00",
        "2026-11-05 00:00", "2026-11-05 05:00",
        "2026-11-06 00:00", "2026-11-06 05:00",
    ]
    out = deduplicate_trading_days(_df(stamps))
    assert len(out) == 3
    assert [ts.strftime("%Y-%m-%d") for ts in out.index] == [
        "2026-11-04", "2026-11-05", "2026-11-06"
    ]
    # Keeps the LATEST stamp per day (freshest provider write).
    assert out.index[0] == pd.Timestamp("2026-11-04 04:00")
    assert out.index[2] == pd.Timestamp("2026-11-06 05:00")


def test_single_stamped_frame_unchanged():
    stamps = ["2026-11-04 00:00", "2026-11-05 00:00", "2026-11-06 00:00"]
    df = _df(stamps)
    out = deduplicate_trading_days(df)
    assert out is df  # no copy, no change
    assert len(out) == 3


def test_empty_frame_is_safe():
    out = deduplicate_trading_days(_df([]))
    assert out.empty
