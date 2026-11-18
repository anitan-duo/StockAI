"""RSI intelligence: point-in-time oscillator analysis and prediction context."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from services.ml.rsi_features import (
    DEFAULT_PERIODS,
    detect_divergence,
    last_crossover,
    rsi_feature_frame,
)

MIN_BARS = 40
SERIES_BARS = 120


def _json_number(value: Any, digits: int = 4) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits)


def _agreement(
    direction: str | None,
    rsi14: float | None,
    slope5: float | None,
) -> dict:
    if direction is None:
        return {
            "status": "unknown",
            "rsi_signal": "unknown",
            "reason": "No production prediction is available for this instrument.",
        }
    if rsi14 is None or slope5 is None:
        return {
            "status": "unknown",
            "rsi_signal": "unknown",
            "reason": "Insufficient RSI history to compare with the prediction.",
        }
    if rsi14 >= 55 and slope5 > 0:
        signal = "bullish"
    elif rsi14 <= 45 and slope5 < 0:
        signal = "bearish"
    else:
        signal = "neutral"
    if direction == signal:
        status = "agrees"
    elif direction == "neutral" and abs(rsi14 - 50) <= 5:
        status = "agrees"
    else:
        status = "disagrees"
    reason = (
        f"Model predicts {direction.upper()}; RSI(14) is {rsi14:.1f} with a 5-day change "
        f"of {slope5:+.1f} points ({signal} momentum). RSI above 70 is not automatically a sell "
        "and below 30 is not automatically a buy."
    )
    return {"status": status, "rsi_signal": signal, "reason": reason}


def analyze_rsi_bars(
    ohlcv: pd.DataFrame,
    prediction_direction: str | None = None,
) -> dict:
    """Analyze RSI from an ascending OHLCV frame (no future data)."""
    if ohlcv is None or ohlcv.empty or "close" not in ohlcv:
        raise ValueError("OHLCV data with close prices is required")
    frame = ohlcv.sort_index()
    if len(frame) < MIN_BARS:
        raise ValueError(
            f"Insufficient history for RSI analysis: need {MIN_BARS}, have {len(frame)}"
        )

    features = rsi_feature_frame(frame, DEFAULT_PERIODS)
    latest = features.iloc[-1]
    close = frame["close"].astype(float)

    current = {
        f"rsi_{period}": _json_number(latest[f"rsi_wilder_{period}"], 2)
        for period in DEFAULT_PERIODS
    }
    slopes = {
        f"slope_5d_{period}": _json_number(latest[f"rsi_slope_5d_{period}"], 3)
        for period in DEFAULT_PERIODS
    }
    roc = {
        f"roc_5d_{period}": _json_number(latest[f"rsi_roc_5d_{period}"], 4)
        for period in DEFAULT_PERIODS
    }
    relative = {
        f"vs_sma_{period}": _json_number(latest[f"rsi_minus_sma_{period}"], 3)
        for period in DEFAULT_PERIODS
    }

    rsi14 = current["rsi_14"]
    slope14 = slopes["slope_5d_14"]
    if rsi14 is None:
        zone = "unavailable"
    elif rsi14 >= 70:
        zone = "overbought"
    elif rsi14 <= 30:
        zone = "oversold"
    else:
        zone = "neutral"

    if slope14 is None:
        trend = "unavailable"
    elif slope14 > 2:
        trend = "rising"
    elif slope14 < -2:
        trend = "falling"
    else:
        trend = "flat"

    persistence = {
        "overbought_days": int(latest.get("rsi_persistence_overbought_14", 0) or 0),
        "oversold_days": int(latest.get("rsi_persistence_oversold_14", 0) or 0),
    }
    regime = {
        "high_volatility": bool(float(latest.get("high_vol_regime", 0) or 0) >= 0.5),
        "uptrend_50_200": bool(float(latest.get("uptrend_regime", 0) or 0) >= 0.5),
        "vol_20d": _json_number(latest.get("vol_20d"), 2),
        "vol_60d": _json_number(latest.get("vol_60d"), 2),
    }

    rsi14_series = features["rsi_wilder_14"]
    crossovers = [last_crossover(rsi14_series, level, lookback=20) for level in (30, 50, 70)]
    divergence = detect_divergence(close, rsi14_series, lookback=min(60, len(frame)))

    tail = features.tail(SERIES_BARS)
    series = []
    for idx, row in tail.iterrows():
        series.append(
            {
                "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "close": _json_number(frame.loc[idx, "close"], 4),
                "rsi_7": _json_number(row.get("rsi_wilder_7"), 3),
                "rsi_14": _json_number(row.get("rsi_wilder_14"), 3),
                "rsi_21": _json_number(row.get("rsi_wilder_21"), 3),
            }
        )

    agreement = _agreement(prediction_direction, rsi14, slope14)

    if zone == "overbought":
        interpretation = (
            f"RSI(14) is {rsi14:.1f} (overbought zone) and {trend}. Overbought conditions describe "
            "strong recent price movement; they do not by themselves imply a reversal or a sell."
        )
    elif zone == "oversold":
        interpretation = (
            f"RSI(14) is {rsi14:.1f} (oversold zone) and {trend}. Oversold conditions describe weak "
            "recent price movement; they do not by themselves imply a bounce or a buy."
        )
    else:
        interpretation = (
            f"RSI(14) is {rsi14:.1f} (neutral zone) and {trend} over the last five sessions."
        )

    return {
        "method": "Wilder RSI (standard smoothing); all values use bars up to the latest close only",
        "periods": list(DEFAULT_PERIODS),
        "thresholds": {"overbought": 70, "oversold": 30},
        "current": current,
        "slopes_5d": slopes,
        "roc_5d": roc,
        "relative_to_mean": relative,
        "zone": zone,
        "trend": trend,
        "persistence": persistence,
        "regime": regime,
        "crossovers": crossovers,
        "divergence": divergence,
        "agreement": agreement,
        "interpretation": interpretation,
        "series": series,
        "bar_count": int(len(frame)),
        "data_timestamp": frame.index[-1].isoformat()
        if hasattr(frame.index[-1], "isoformat")
        else str(frame.index[-1]),
        "caveats": [
            "RSI is a technical momentum measure, not a recommendation. Overbought/oversold are descriptive zones.",
            "Divergence uses the two most recent confirmed swing points; it can be absent in choppy markets.",
            "v1.0 has no verified fundamental, sector-relative, or point-in-time macro features to condition RSI on.",
        ],
    }
