"""Point-in-time RSI feature engineering and interpretation.

RSI is an oscillator, not a buy/sell switch. Every function here uses only
past and current bars (rolling/shift), so it is safe for walk-forward research
and inference. Wilder's smoothing is used for the RSI shown to users; the
frozen 87-feature production schema keeps its original simple-average RSI
features so the champion artifact remains valid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PERIODS = (7, 14, 21)


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (standard TA definition).

    First average is the simple mean of the first `period` changes; thereafter
    avg = (prev_avg * (period - 1) + current) / period. Flat markets return 50,
    a zero average loss with positive gains returns 100.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return out

    avg_gain = float(gain.iloc[1 : period + 1].mean())
    avg_loss = float(loss.iloc[1 : period + 1].mean())
    out.iloc[period] = _rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + float(gain.iloc[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(loss.iloc[i])) / period
        out.iloc[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_feature_frame(
    ohlcv: pd.DataFrame,
    periods: tuple[int, ...] = DEFAULT_PERIODS,
) -> pd.DataFrame:
    """RSI family features from OHLCV (no future information)."""
    close = ohlcv["close"].astype(float)
    features = pd.DataFrame(index=ohlcv.index)

    for period in periods:
        col = f"rsi_wilder_{period}"
        features[col] = wilder_rsi(close, period)
        features[f"rsi_slope_5d_{period}"] = features[col] - features[col].shift(5)
        features[f"rsi_roc_5d_{period}"] = features[col].pct_change(5)
        features[f"rsi_minus_sma_{period}"] = features[col] - features[col].rolling(period).mean()
        features[f"rsi_overbought_{period}"] = (features[col] > 70).astype(float)
        features[f"rsi_oversold_{period}"] = (features[col] < 30).astype(float)

    rsi14 = features["rsi_wilder_14"]
    over = (rsi14 > 70).astype(int)
    under = (rsi14 < 30).astype(int)
    features["rsi_persistence_overbought_14"] = _run_length(over)
    features["rsi_persistence_oversold_14"] = _run_length(under)

    returns = close.pct_change()
    vol_20 = returns.rolling(20).std() * np.sqrt(252)
    vol_60 = returns.rolling(60).std() * np.sqrt(252)
    high_vol = (vol_20 > vol_60 * 1.2).astype(float)
    features["rsi14_x_high_vol"] = rsi14 * high_vol
    features["rsi14_slope_x_high_vol"] = features["rsi_slope_5d_14"] * high_vol

    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    uptrend = (sma50 > sma200).astype(float)
    features["rsi14_x_uptrend"] = rsi14 * uptrend
    features["rsi14_slope_x_uptrend"] = features["rsi_slope_5d_14"] * uptrend

    features["vol_20d"] = vol_20
    features["vol_60d"] = vol_60
    features["high_vol_regime"] = high_vol
    features["uptrend_regime"] = uptrend
    return features


def _run_length(flags: pd.Series) -> pd.Series:
    out = np.zeros(len(flags), dtype=float)
    run = 0
    for i, flag in enumerate(flags.fillna(0).astype(int).to_numpy()):
        run = run + 1 if flag else 0
        out[i] = float(run)
    return pd.Series(out, index=flags.index)


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    return wilder_rsi(close, period)


def find_swings(values: np.ndarray, wing: int = 2) -> list[tuple[int, float]]:
    """Local extrema: index is strictly highest/lowest within +/- wing."""
    swings: list[tuple[int, float]] = []
    for i in range(wing, len(values) - wing):
        window = values[i - wing : i + wing + 1]
        if not np.all(np.isfinite(window)):
            continue
        if values[i] == np.max(window) or values[i] == np.min(window):
            swings.append((i, float(values[i])))
    return swings


def detect_divergence(
    close: pd.Series,
    rsi: pd.Series,
    lookback: int = 60,
    wing: int = 2,
) -> dict:
    """Deterministic swing-based divergence detection.

    Compares the two most recent swing highs and lows in the lookback window.
    Bearish: price makes a higher high while RSI makes a lower high.
    Bullish: price makes a lower low while RSI makes a higher low.
    """
    close_tail = close.astype(float).tail(lookback)
    rsi_tail = rsi.astype(float).tail(lookback)
    prices = close_tail.to_numpy()
    rs = rsi_tail.to_numpy()
    if len(prices) < wing * 2 + 3:
        return {
            "detected": False,
            "kind": "none",
            "method": "two most recent confirmed price/RSI swing points (lookback=60, wing=2)",
            "reason": "Insufficient bars for divergence detection.",
        }

    highs_idx = []
    lows_idx = []
    for i in range(wing, len(prices) - wing):
        window = prices[i - wing : i + wing + 1]
        if not np.all(np.isfinite(window)):
            continue
        if prices[i] == np.max(window):
            highs_idx.append(i)
        if prices[i] == np.min(window):
            lows_idx.append(i)

    if len(highs_idx) >= 2:
        a, b = highs_idx[-2], highs_idx[-1]
        if np.isfinite(rs[a]) and np.isfinite(rs[b]) and prices[b] > prices[a] and rs[b] < rs[a]:
            return {
                "detected": True,
                "kind": "bearish",
                "method": "two most recent confirmed price/RSI swing highs (lookback=60, wing=2)",
                "reason": f"Price made a higher high ({prices[a]:.2f} → {prices[b]:.2f}) while RSI made a lower high ({rs[a]:.1f} → {rs[b]:.1f}).",
                "price_points": [float(prices[a]), float(prices[b])],
                "rsi_points": [float(rs[a]), float(rs[b])],
            }

    if len(lows_idx) >= 2:
        a, b = lows_idx[-2], lows_idx[-1]
        if np.isfinite(rs[a]) and np.isfinite(rs[b]) and prices[b] < prices[a] and rs[b] > rs[a]:
            return {
                "detected": True,
                "kind": "bullish",
                "method": "two most recent confirmed price/RSI swing lows (lookback=60, wing=2)",
                "reason": f"Price made a lower low ({prices[a]:.2f} → {prices[b]:.2f}) while RSI made a higher low ({rs[a]:.1f} → {rs[b]:.1f}).",
                "price_points": [float(prices[a]), float(prices[b])],
                "rsi_points": [float(rs[a]), float(rs[b])],
            }

    return {
        "detected": False,
        "kind": "none",
        "method": "two most recent confirmed price/RSI swing points (lookback=60, wing=2)",
        "reason": "No qualifying price/RSI divergence in the lookback window.",
    }


def last_crossover(rsi: pd.Series, level: float, lookback: int = 20) -> dict:
    """Most recent crossing of an RSI level within the lookback window."""
    tail = rsi.astype(float).tail(lookback + 1)
    if len(tail) < 2:
        return {"detected": False, "level": level}
    prev = tail.shift(1)
    above = (tail > level) & (prev <= level)
    below = (tail < level) & (prev >= level)
    hits = list(tail.index[above | below])
    if not hits:
        return {"detected": False, "level": level}
    idx = hits[-1]
    direction = "above" if bool(above.loc[idx]) else "below"
    position = list(tail.index).index(idx)
    return {
        "detected": True,
        "level": level,
        "direction": direction,
        "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
        "bars_ago": len(tail) - 1 - position,
    }
