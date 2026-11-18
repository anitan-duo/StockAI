"""Market session awareness (spec §21).

Derives a market's session status from the Market model's timezone and
trading hours. This is deliberately a pure function over data any caller
already has — providers run without DB access, routes have the ORM row.

Known limitation (documented in ARCHITECTURE.md): exchange holidays are
not modeled; a holiday during a weekday reports the session as open.
Weekends are always closed.

Timestamps are UTC internally; conversion happens only via the market's
IANA timezone at the presentation/classification boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SessionBounds:
    """UTC bounds of a market's sessions on a given local date."""

    regular_open_utc: datetime
    regular_close_utc: datetime
    pre_open_utc: Optional[datetime] = None
    post_close_utc: Optional[datetime] = None


def _combine(local_date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(local_date, t, tzinfo=tz).astimezone(UTC)


def session_bounds(market, local_date=None) -> SessionBounds:
    """UTC session bounds for a Market on a local calendar date.

    `market` is the ORM Market (or any object with timezone, market_open,
    market_close, pre_market_open, post_market_close attributes).
    """
    tz = ZoneInfo(market.timezone)
    if local_date is None:
        local_date = datetime.now(tz).date()
    return SessionBounds(
        regular_open_utc=_combine(local_date, market.market_open, tz),
        regular_close_utc=_combine(local_date, market.market_close, tz),
        pre_open_utc=(
            _combine(local_date, market.pre_market_open, tz)
            if market.pre_market_open
            else None
        ),
        post_close_utc=(
            _combine(local_date, market.post_market_close, tz)
            if market.post_market_close
            else None
        ),
    )


def derive_market_status(market, now: Optional[datetime] = None) -> str:
    """Session status: pre-market | open | after-hours | closed.

    Weekends are closed. Holidays are not modeled (limitation documented
    above). Never infers state from "an API returned a value".
    """
    if now is None:
        now = datetime.now(UTC)
    tz = ZoneInfo(market.timezone)
    local = now.astimezone(tz)
    if local.weekday() >= 5:  # Saturday/Sunday in market-local time
        return "closed"

    b = session_bounds(market, local.date())
    if b.regular_open_utc <= now < b.regular_close_utc:
        return "open"
    if b.pre_open_utc is not None and b.pre_open_utc <= now < b.regular_open_utc:
        return "pre-market"
    if b.post_close_utc is not None and b.regular_close_utc <= now < b.post_close_utc:
        return "after-hours"
    # Without explicit post-market bounds, the gap between close and the
    # next pre-open is simply closed.
    return "closed"


def refine_source_timestamp(
    source_ts: datetime, market, metadata: Optional[dict] = None, now: Optional[datetime] = None
) -> tuple[datetime, bool]:
    """Refine a provider source timestamp that only carries a date.

    Alpha Vantage's GLOBAL_QUOTE exposes only "latest trading day". For a
    same-day quote the true source instant lies between session open and
    now; using midnight overstates the age (a fresh afternoon quote would
    classify as stale). Clamping to the session open claims "no newer than
    session open" — a provable lower bound that can never overstate
    freshness.

    Returns (refined_timestamp, refined) — refined=False means the caller
    should use source_ts unchanged.
    """
    if not metadata or not metadata.get("source_date_only"):
        return source_ts, False

    if now is None:
        now = datetime.now(UTC)
    tz = ZoneInfo(market.timezone)
    local_now = now.astimezone(tz)
    source_local = source_ts.astimezone(tz)

    if source_local.date() < local_now.date():
        # Prior session: midnight of the trading day is already the honest
        # conservative instant (data is from that session at the latest).
        return source_ts, False

    # Same trading day: the newest the data can be is now, the oldest
    # provable instant is the session open.
    b = session_bounds(market, source_local.date())
    if b.regular_open_utc > now:
        # Session not yet open on the reported trading day — the date-only
        # claim cannot be reconciled with the calendar; keep the raw date.
        return source_ts, False
    clamped = max(source_ts, b.regular_open_utc)
    return clamped, True
