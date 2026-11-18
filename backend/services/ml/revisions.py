"""Analyst-revision features — P18-E025 (Track A: new information).

Pure, deterministic, causally safe: every feature for a row dated D uses only
revisions dated <= D. ALWAYS PRESENT: symbols without revision history receive
explicit sentinel values, preserving 100% eligible-row coverage.

Source: yfinance `upgrades_downgrades` snapshot (research/data/revisions/,
hash-verified manifest) — authorized, free.

Features (5):
  rev_days_since    calendar days since last revision, capped at CAP_DAYS
  rev_last_delta    grade-score change of the last revision (clipped)
  rev_net_63        net grade-score change over trailing 63 calendar days
  rev_count_63      number of revisions over trailing 63 calendar days
  rev_up_share_63   fraction of trailing-63-day revisions that were upgrades
"""

from __future__ import annotations

from datetime import date, datetime

FEATURE_NAMES = (
    "rev_days_since",
    "rev_last_delta",
    "rev_net_63",
    "rev_count_63",
    "rev_up_share_63",
)

CAP_DAYS = 365.0
WINDOW_DAYS = 63
DELTA_CLIP = 3.0

_GRADE_SCORE = {
    "strong buy": 5.0, "buy": 4.0, "overweight": 4.0, "outperform": 4.0,
    "market outperform": 4.0, "positive": 4.0, "accumulate": 4.0,
    "hold": 3.0, "neutral": 3.0, "equal-weight": 3.0, "equal weight": 3.0,
    "market perform": 3.0, "sector perform": 3.0, "in-line": 3.0,
    "peer perform": 3.0, "marketweight": 3.0,
    "underperform": 2.0, "underweight": 2.0, "sell": 2.0, "reduce": 2.0,
    "negative": 2.0, "market underperform": 2.0,
    "strong sell": 1.0,
}


def grade_score(grade: str):
    if not grade:
        return None
    return _GRADE_SCORE.get(grade.strip().lower())


def _delta(row: dict) -> float:
    """Signed revision strength: grade-score change if both grades known,
    else +1 (up/init) / -1 (down) from the Action field."""
    a = grade_score(row.get("to_grade", ""))
    b = grade_score(row.get("from_grade", ""))
    if a is not None and b is not None:
        return max(-DELTA_CLIP, min(DELTA_CLIP, a - b))
    act = (row.get("action") or "").strip().lower()
    if act == "up":
        return 1.0
    if act == "down":
        return -1.0
    return 0.0


def build_entries(rows: list[dict]) -> list[tuple]:
    """Rows -> sorted (date, delta) list."""
    out = []
    for r in rows:
        try:
            d = datetime.strptime(r["date"][:10], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        out.append((d, _delta(r)))
    out.sort(key=lambda e: e[0])
    return out


def _as_date(asof) -> date:
    if isinstance(asof, datetime):
        return asof.date()
    if isinstance(asof, date):
        return asof
    raise ValueError("asof must be a date/datetime")


def lookup(entries: list[tuple], asof) -> dict[str, float]:
    """Always-present revision features usable at ``asof`` (no None path)."""
    d = _as_date(asof)
    past = [(ed, dl) for ed, dl in entries if ed <= d]
    if not past:
        return {n: 0.0 for n in FEATURE_NAMES} | {"rev_days_since": CAP_DAYS}
    last_date, last_delta = past[-1]
    days = float(min((d - last_date).days, CAP_DAYS))
    win = [(ed, dl) for ed, dl in past if (d - ed).days <= WINDOW_DAYS]
    net = max(-10.0, min(10.0, sum(dl for _e, dl in win)))
    cnt = float(len(win))
    ups = float(sum(1 for _e, dl in win if dl > 0))
    share = (ups / cnt) if cnt else 0.0
    return {
        "rev_days_since": days,
        "rev_last_delta": max(-DELTA_CLIP, min(DELTA_CLIP, last_delta)),
        "rev_net_63": net,
        "rev_count_63": cnt,
        "rev_up_share_63": share,
    }
