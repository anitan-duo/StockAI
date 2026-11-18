"""Cross-sectional market context (P6 information-set experiment).

Pure, deterministic, causally safe: every feature for a row dated D uses only
panel bars with timestamp <= D. No imputation (fail closed -> None), no
randomness, no I/O. Operates on (timestamp, close) pairs so frozen research
snapshots and live bars share the exact code path.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean, pstdev

FEATURE_NAMES = (
    "xs_excess_ret_20d",
    "xs_rel_strength_60d",
    "xs_rank_20d",
    "xs_dispersion_20d",
    "xs_mkt_vol_20d",
    "xs_breadth_60d",
)

MIN_SYMBOLS = 15  # of the 19-symbol panel; fewer -> None (fail closed)


def _closes_at_or_before(
    series: list[tuple[datetime, float]], asof: datetime, n: int
) -> list[float] | None:
    """Last n closes with timestamp <= asof, newest-first. None if short."""
    out: list[float] = []
    for ts, close in reversed(series):
        if ts <= asof:
            out.append(close)
            if len(out) == n:
                break
    return out if len(out) == n else None


def cross_sectional_context(
    panel: dict[str, list[tuple[datetime, float]]],
    symbol: str,
    asof: datetime,
) -> dict[str, float] | None:
    """Six market-context features for ``symbol`` as of ``asof``.

    Returns None when the panel cannot support the computation (too few
    symbols, missing history, non-positive prices) — callers must skip the
    row/eval, never substitute.
    """
    if symbol not in panel:
        return None
    # Per-symbol trailing windows, strictly historical.
    rets_20: dict[str, float] = {}
    rets_60: dict[str, float] = {}
    daily_market: list[float] = []  # equal-weight daily means, 20 deep
    for sym, series in panel.items():
        w61 = _closes_at_or_before(series, asof, 61)
        if w61 is None:
            continue
        if any(c <= 0 for c in w61):
            continue
        r20 = w61[0] / w61[20] - 1.0
        r60 = w61[0] / w61[60] - 1.0
        rets_20[sym] = r20
        rets_60[sym] = r60
    if len(rets_20) < MIN_SYMBOLS or symbol not in rets_20:
        return None
    # Daily market means for volatility: day-d mean of per-symbol 1d returns.
    for d in range(20):
        day_rets: list[float] = []
        for sym, series in panel.items():
            w = _closes_at_or_before(series, asof, d + 2)
            if w is None or w[1] <= 0:
                continue
            day_rets.append(w[0] / w[1] - 1.0)
        if len(day_rets) < MIN_SYMBOLS:
            return None
        daily_market.append(mean(day_rets))
    vals_20 = list(rets_20.values())
    vals_60 = list(rets_60.values())
    mkt_20 = mean(vals_20)
    below = sum(1 for v in vals_20 if v < rets_20[symbol])
    return {
        "xs_excess_ret_20d": rets_20[symbol] - mkt_20,
        "xs_rel_strength_60d": rets_60[symbol] - mean(vals_60),
        "xs_rank_20d": below / len(vals_20),
        "xs_dispersion_20d": pstdev(vals_20) if len(vals_20) > 1 else 0.0,
        "xs_mkt_vol_20d": pstdev(daily_market) if len(daily_market) > 1 else 0.0,
        "xs_breadth_60d": sum(1 for v in vals_60 if v > 0) / len(vals_60),
    }
