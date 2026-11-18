"""Point-in-time US fundamentals features (E011 information experiment).

Pure, deterministic, causally safe: every feature for a row dated D uses only
filings with filedDate <= D (via research.pit availability semantics).
Filings come from the frozen Finnhub as-reported snapshot
(research/data/fundamentals_us/, hash-verified manifest) — US SEC filers only;
any symbol without filings yields None (fail closed -> row skipped, never
imputed).

Features (3, quarterly cadence):
  fund_rev_growth_yoy: revenue vs the report 4 filings back by period-end
    order (≈1 year earlier; fiscal-cadence assumption documented, not validated
    per-filer — a wrong-cadence match only adds noise, never future info,
    because gating is by filedDate regardless).
  fund_net_margin: net income / revenue from the same gated report.
  fund_days_since_filing: (row_date - filedDate).days of the gated report
    (event-recency proxy; filing-day drift effects decay with this).
"""

from __future__ import annotations

from datetime import UTC, datetime

FEATURE_NAMES = (
    "fund_rev_growth_yoy",
    "fund_net_margin",
    "fund_days_since_filing",
)

REVENUE_CONCEPTS = (
    "us-gaap_Revenues",
    "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap_SalesRevenueNet",
)
NET_INCOME_CONCEPT = "us-gaap_NetIncomeLoss"


def _parse_ts(s: str | None) -> datetime | None:
    """Parse 'YYYY-MM-DD HH:MM:SS' (Finnhub) as UTC. None if unparseable."""
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(s.strip()[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt.replace(tzinfo=UTC)


def _concept_value(report: dict, concepts: tuple[str, ...]) -> float | None:
    """First available concept value across sections (ic/bs/cf), else None."""
    sections = (report.get("report") or {})
    for sec in ("ic", "bs", "cf"):
        for row in sections.get(sec, []) or []:
            if row.get("concept") in concepts and isinstance(row.get("value"), (int, float)):
                return float(row["value"])
    return None


def extract_reports(payload: dict) -> list[dict]:
    """Flatten one frozen Finnhub as-reported payload to report dicts.

    Reports missing filedDate are DROPPED (no availability provable).
    Reports missing revenue or net income are kept with None values so
    coverage reporting can distinguish 'no filing' from 'filing w/o metric'.
    """
    out = []
    for r in payload.get("data", []) or []:
        filed = _parse_ts(r.get("filedDate"))
        if filed is None:
            continue
        out.append({
            "filedDate": filed,
            "endDate": (r.get("endDate") or "")[:10],
            "form": r.get("form"),
            "quarter": r.get("quarter"),
            "year": r.get("year"),
            "revenue": _concept_value(r, REVENUE_CONCEPTS),
            "net_income": _concept_value(r, (NET_INCOME_CONCEPT,)),
        })
    return out


def _yoy_base(reports: list[dict], i: int) -> float | None:
    """Revenue of the same quarter one year earlier (anniversary match).

    Quarterly files omit Q4 for many filers (covered by the 10-K instead), so
    positional 4-back compares mismatched quarters (verified: AAPL Q1'21 vs a
    non-Q1 base gave −0.43 instead of +0.21). Match on vendor (quarter, year−1)
    first, else period-end anniversary within 345–385 days; else None.
    Anniversary matching only selects WHICH past report to compare — gating
    by filedDate is unchanged, so no future information can enter.
    """
    r = reports[i]
    if r["quarter"] is not None and r["year"] is not None:
        for j in range(i):
            q = reports[j]
            if q["quarter"] == r["quarter"] and q["year"] == r["year"] - 1:
                if q["revenue"]:
                    return q["revenue"]
                break
    try:
        end = datetime.strptime(r["endDate"], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    for j in range(i):
        try:
            prev = datetime.strptime(reports[j]["endDate"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if 345 <= (end - prev).days <= 385 and reports[j]["revenue"]:
            return reports[j]["revenue"]
    return None


def build_entries(reports: list[dict]) -> list[tuple]:
    """Sort by period end; attach YoY growth vs 4-back and margin.

    Returns list of (filedDate, revenue, net_income, rev_growth_yoy|None,
    net_margin|None) in filedDate order. Growth needs a 4-back report with
    positive revenues; margin needs nonzero revenue — else None (fail closed
    downstream, never zero-filled).
    """
    ordered = sorted([r for r in reports if r["endDate"]], key=lambda r: r["endDate"])
    entries = []
    for i, r in enumerate(ordered):
        rev, ni = r["revenue"], r["net_income"]
        yoy = None
        if rev and rev > 0:
            base = _yoy_base(ordered, i)
            if base and base > 0:
                yoy = rev / base - 1.0
        margin = (ni / rev) if (rev and rev != 0 and ni is not None) else None
        entries.append((r["filedDate"], rev, ni, yoy, margin))
    entries.sort(key=lambda e: e[0])
    return entries


def lookup(entries: list[tuple], asof: datetime) -> dict[str, float] | None:
    """Latest entry with filedDate <= asof AND both computed features present.

    Returns None when no gated report supports the full feature set (callers
    must skip the row/eval, never substitute). asof must be tz-aware.
    """
    if asof is None or asof.tzinfo is None:
        raise ValueError("lookup asof must be tz-aware (fail closed)")
    best = None
    for filed, _rev, _ni, yoy, margin in entries:
        if filed <= asof and yoy is not None and margin is not None:
            best = (filed, yoy, margin)
    if best is None:
        return None
    filed, yoy, margin = best
    return {
        "fund_rev_growth_yoy": yoy,
        "fund_net_margin": margin,
        "fund_days_since_filing": float((asof - filed).days),
    }


EVENT_FEATURE_NAMES = ("fund_event_5d",)


def event_lookup(entries: list[tuple], asof: datetime, window_days: int = 5) -> dict[str, float] | None:
    """Binary filing-event marker (P12): 1.0 iff ANY report in ``entries`` has
    filedDate <= asof within the last ``window_days`` calendar days.

    Marker gating needs filedDate ONLY (not the full computed feature set),
    so coverage strictly exceeds lookup(). No gated filing at all -> None
    (callers must skip, never default to 0.0 — absence of data is not
    absence of an event). asof must be tz-aware.
    """
    if asof is None or asof.tzinfo is None:
        raise ValueError("event_lookup asof must be tz-aware (fail closed)")
    if window_days < 0:
        raise ValueError("window_days must be non-negative")
    seen_any = False
    for filed, _rev, _ni, _yoy, _margin in entries:
        if filed <= asof:
            seen_any = True
            if (asof - filed).days <= window_days:
                return {"fund_event_5d": 1.0}
    if not seen_any:
        return None
    return {"fund_event_5d": 0.0}
