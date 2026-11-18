"""Earnings-surprise (PEAD) features — P18-E022 (Track A: new information).

Pure, deterministic, causally safe: every feature for a row dated D uses only
announcements with announce_date <= D. Unlike fundamentals (fail-closed on
missing filings), these features are ALWAYS PRESENT: symbols without earnings
history receive explicit sentinel values, so 100% eligible-row coverage is
preserved (no row is ever dropped or imputed from the future).

Source: yfinance `get_earnings_dates` snapshot (research/data/earnings/,
hash-verified manifest) — authorized, free. A surprise becomes usable only
on/after its announcement date.

Features (4):
  earn_days_since       calendar days since last announcement, capped at
                        CAP_DAYS (sentinel CAP_DAYS before the first event)
  earn_last_surprise    surprise % of the last announcement, clipped to
                        +/-SURPRISE_CLIP; 0.0 before the first event
  earn_in_window        1.0 iff 0 <= days_since <= WINDOW_DAYS
  earn_surprise_recent  earn_last_surprise * earn_in_window
"""

from __future__ import annotations

from datetime import date, datetime

FEATURE_NAMES = (
    "earn_days_since",
    "earn_last_surprise",
    "earn_in_window",
    "earn_surprise_recent",
)

CAP_DAYS = 365.0
WINDOW_DAYS = 5
SURPRISE_CLIP = 50.0


def build_entries(rows: list[dict]) -> list[tuple]:
    """Rows ({symbol, announce_date, surprise_pct}) -> sorted (date, surprise) list.

    surprise_pct blank/unparseable -> None (still a valid event for recency).
    """
    out = []
    for r in rows:
        try:
            d = datetime.strptime(r["announce_date"][:10], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        raw = r.get("surprise_pct", "")
        try:
            sur = float(raw) if raw not in ("", None) else None
        except (TypeError, ValueError):
            sur = None
        out.append((d, sur))
    out.sort(key=lambda e: e[0])
    return out


def _as_date(asof) -> date:
    if isinstance(asof, datetime):
        return asof.date()
    if isinstance(asof, date):
        return asof
    raise ValueError("asof must be a date/datetime")


def lookup(entries: list[tuple], asof) -> dict[str, float]:
    """Always-present earnings features usable at ``asof`` (no None path)."""
    d = _as_date(asof)
    last = None
    for adate, sur in entries:
        if adate <= d:
            last = (adate, sur)
        else:
            break
    if last is None:
        return {"earn_days_since": CAP_DAYS, "earn_last_surprise": 0.0,
                "earn_in_window": 0.0, "earn_surprise_recent": 0.0}
    adate, sur = last
    days = float(min((d - adate).days, CAP_DAYS))
    sur = 0.0 if sur is None else max(-SURPRISE_CLIP, min(SURPRISE_CLIP, float(sur)))
    in_win = 1.0 if days <= WINDOW_DAYS else 0.0
    return {"earn_days_since": days, "earn_last_surprise": sur,
            "earn_in_window": in_win, "earn_surprise_recent": sur * in_win}
