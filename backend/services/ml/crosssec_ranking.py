"""Cross-sectional relative-performance ranking primitives.

The research task (P18-E021/E026) is *relative*: for session d and symbol s,
the label is 1 iff the forward H-session return exceeds the cross-sectional
median over the eligible universe. This module owns the shared construction
used by research training, evaluation and production inference so the two
paths cannot drift:

* causal per-symbol features from :class:`FeaturePipeline`;
* three cross-sectional trailing-return percentile descriptors (1/5/20);
* forward-return labels and the eligible-universe median;
* deterministic scoring of one as-of session.

Scores are probabilities of *outperforming the same-session cross-sectional
median* — not probabilities that a stock rises in absolute terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

from services.ml.features import FeaturePipeline

RANKING_OBJECTIVE = "cross_sectional_relative_performance"
RANKING_FEATURE_VERSION = "v1"
RANK_DESCRIPTOR_WINDOWS = (1, 5, 20)
DESCRIPTOR_NAMES = tuple(f"xs_rank_{w}d" for w in RANK_DESCRIPTOR_WINDOWS)
MIN_ELIGIBLE_SYMBOLS = 6


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def bars_to_frame(bars: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Normalize bars to a de-duplicated, date-indexed OHLCV frame."""
    rows = []
    for b in bars:
        rows.append(
            {
                "date": _as_date(b.get("date", b.get("timestamp"))),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "volume": float(b["volume"]),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).sort_values("date")
    # One row per session day: keep the freshest observation deterministically.
    df = df.groupby("date", sort=True, as_index=False).tail(1)
    df = df.set_index(pd.DatetimeIndex(pd.to_datetime(df["date"])))
    return df[["open", "high", "low", "close", "volume"]]


def compute_symbol_features(bars: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Causal 87-feature matrix for one symbol (same pipeline as research)."""
    ohlcv = bars_to_frame(bars)
    if ohlcv.empty:
        return ohlcv
    return FeaturePipeline().compute_all_features(ohlcv)


def rank_of(value: float, values: list[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.5
    below = sum(1 for v in values if v < value)
    return below / (n - 1)


def _trailing_return(close: pd.Series, window: int) -> pd.Series:
    return close / close.shift(window) - 1.0


def _descriptor_table(closes: dict[str, pd.Series]) -> dict[tuple[str, date, int], float]:
    """Percentile rank of each symbol's trailing return on each date."""
    out: dict[tuple[str, date, int], float] = {}
    for window in RANK_DESCRIPTOR_WINDOWS:
        by_date: dict[date, dict[str, float]] = {}
        for symbol, close in closes.items():
            trail = _trailing_return(close.astype(float), window)
            for ts, value in trail.items():
                if pd.isna(value):
                    continue
                d = _as_date(ts)
                by_date.setdefault(d, {})[symbol] = float(value)
        for d, values in by_date.items():
            vals = list(values.values())
            for symbol, value in values.items():
                out[(symbol, d, window)] = rank_of(value, vals)
    return out


@dataclass
class RankingDataset:
    frame: pd.DataFrame
    feature_names: list[str]
    symbols: list[str]
    markets: dict[str, str]
    horizon: int

    @property
    def n_rows(self) -> int:
        return len(self.frame)


def build_ranking_dataset(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    markets: dict[str, str],
    horizon: int,
    max_rows_per_symbol: int | None = None,
    min_eligible: int = MIN_ELIGIBLE_SYMBOLS,
) -> RankingDataset:
    """Build the causal long-form training/evaluation dataset.

    Features at row d use only bars <= d. The label at d uses the forward
    H-session return and the same-session cross-sectional median over symbols
    with both a feature row and a forward return.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    symbols = sorted(s for s, bars in bars_by_symbol.items() if bars)
    ohlcv = {s: bars_to_frame(bars_by_symbol[s]) for s in symbols}
    frames = {s: compute_symbol_features(bars_by_symbol[s]) for s in symbols}
    frames = {s: f for s, f in frames.items() if not f.empty and not ohlcv[s].empty}
    symbols = sorted(frames)
    if not symbols:
        raise ValueError("no symbol has usable bars")

    feature_names = [c for c in frames[symbols[0]].columns if not c.startswith("xs_rank_")]
    for s in symbols:
        if list(frames[s].columns) != list(frames[symbols[0]].columns):
            raise ValueError(f"feature schema drift for {s}")

    close_by_symbol: dict[str, pd.Series] = {
        s: ohlcv[s]["close"].astype(float) for s in symbols
    }
    descriptors = _descriptor_table(close_by_symbol)
    fwd: dict[tuple[str, date], float] = {}
    for s, close in close_by_symbol.items():
        for j in range(len(close) - horizon):
            if close.iloc[j] and not pd.isna(close.iloc[j]):
                fwd[(s, _as_date(close.index[j]))] = float(
                    close.iloc[j + horizon] / close.iloc[j] - 1.0
                )

    labels: dict[tuple[str, date], int] = {}
    median_by_date: dict[date, float] = {}
    for s, d in fwd:
        median_by_date.setdefault(d, np.nan)
    by_date: dict[date, list[float]] = {}
    for (s, d), value in fwd.items():
        by_date.setdefault(d, []).append(value)
    for d, vals in by_date.items():
        if len(vals) >= min_eligible:
            median_by_date[d] = float(np.median(vals))
    for (s, d), value in fwd.items():
        med = median_by_date.get(d)
        if med is not None and not pd.isna(med):
            labels[(s, d)] = 1 if value > med else 0

    rows: list[dict[str, Any]] = []
    for s in symbols:
        feat = frames[s]
        span = feat.index
        for j, ts in enumerate(span):
            d = _as_date(ts)
            if (s, d) not in labels:
                continue
            row = feat.iloc[j]
            if row.isna().any():
                continue
            values = row[feature_names].astype(float).tolist()
            values.extend(
                descriptors.get((s, d, w), 0.5) for w in RANK_DESCRIPTOR_WINDOWS
            )
            rows.append(
                {
                    "symbol": s,
                    "market": markets.get(s, "UNKNOWN"),
                    "date": d,
                    "fwd_return": fwd[(s, d)],
                    "label": labels[(s, d)],
                    **dict(zip(feature_names + list(DESCRIPTOR_NAMES), values, strict=True)),
                    "_position": j,
                }
            )

    frame = pd.DataFrame(rows)
    if max_rows_per_symbol is not None and not frame.empty:
        frame = (
            frame.sort_values(["symbol", "date"])
            .groupby("symbol", group_keys=False)
            .tail(max_rows_per_symbol)
            .reset_index(drop=True)
        )
    if frame.empty:
        raise ValueError("dataset is empty after feature/label eligibility filters")

    return RankingDataset(
        frame=frame,
        feature_names=feature_names + list(DESCRIPTOR_NAMES),
        symbols=symbols,
        markets=markets,
        horizon=horizon,
    )


def score_cross_section(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    markets: dict[str, str],
    as_of: date,
    feature_names: list[str],
    horizon: int,
) -> tuple[list[str], np.ndarray, dict[str, str]]:
    """Build the as-of feature matrix for the eligible universe.

    Returns (eligible symbols, X, exclusion reasons). Bars after ``as_of`` are
    discarded; symbols with no bar on the as-of session, insufficient feature
    history, or NaN features are excluded with a reason.
    """
    eligible: list[str] = []
    excluded: dict[str, str] = {}
    rows: dict[str, np.ndarray] = {}
    feats: dict[str, pd.DataFrame] = {}
    closes: dict[str, pd.Series] = {}

    for symbol, bars in sorted(bars_by_symbol.items()):
        cut = sorted(
            (b for b in bars if _as_date(b.get("date", b.get("timestamp"))) <= as_of),
            key=lambda b: _as_date(b.get("date", b.get("timestamp"))),
        )
        if not cut:
            excluded[symbol] = "no_bars"
            continue
        if _as_date(cut[-1].get("date", cut[-1].get("timestamp"))) != as_of:
            excluded[symbol] = "stale_last_bar"
            continue
        ohlcv = bars_to_frame(cut)
        feat = compute_symbol_features(cut)
        if feat.empty or ohlcv.empty or len(feat.index) < 1:
            excluded[symbol] = "insufficient_history"
            continue
        feats[symbol] = feat
        closes[symbol] = ohlcv["close"].astype(float)

    descriptors = _descriptor_table(closes)

    for symbol, feat in sorted(feats.items()):
        last = feat.iloc[-1]
        if _as_date(feat.index[-1]) != as_of:
            excluded[symbol] = "feature_date_mismatch"
            continue
        values: list[float] = []
        missing = False
        for name in feature_names:
            if name in DESCRIPTOR_NAMES:
                window = int(name.removeprefix("xs_rank_").removesuffix("d"))
                values.append(descriptors.get((symbol, as_of, window), 0.5))
                continue
            if name not in last.index or pd.isna(last[name]):
                missing = True
                break
            values.append(float(last[name]))
        if missing:
            excluded[symbol] = "missing_features"
            continue
        rows[symbol] = np.asarray(values, dtype=float)
        eligible.append(symbol)

    if not eligible:
        return [], np.empty((0, len(feature_names))), excluded
    X = np.vstack([rows[s] for s in eligible])
    return eligible, X, excluded


def predict_outperformance(artifact: dict[str, Any], X: np.ndarray) -> np.ndarray:
    """Average ensemble P(relative label = 1) for each row of X."""
    scaler = artifact["scaler"]
    Xs = scaler.transform(X)
    probs = []
    for model, calibrator in artifact["models"].values():
        p = (calibrator if calibrator is not None else model).predict_proba(Xs)[:, 1]
        probs.append(np.asarray(p, dtype=float))
    if not probs:
        raise ValueError("artifact has no fitted models")
    return np.mean(np.vstack(probs), axis=0)
