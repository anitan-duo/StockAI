"""Canonical trading-day stamping for daily price bars (BAR-002).

Providers stamp the same trading day with different instants:
Alpha Vantage gives naive calendar dates (relabelled UTC by callers),
Twelve Data gives naive/tz calendar datetimes (midnight),
Finnhub returns epoch seconds (UTC-midnight for daily resolution),
Yahoo returns midnight in the EXCHANGE's timezone converted to UTC
(EDT/EST US sessions stamp 04:00/05:00 UTC, IST sessions stamp
18:30 UTC of the previous day, CET sessions stamp 23:00/22:00 UTC).

All of these describe ONE session day. Persisting more than one
instant per (instrument, session day) double-stamps price_bars and
lets features, dedupe and evaluation denominators disagree.

Canonical form: ONE instant per session day — exchange-local midnight
of the session day, converted to UTC — matching what Yahoo (this
system's primary ingest source) already stores, so existing rows stay
valid and only the inconsistent ones are remapped.

Session-day attribution uses only the stamp and the exchange tz:
  * naive stamp (no tzinfo): the date IS the session date (provider
    calendar label) — never re-localize the instant.
  * tz-aware stamp at exactly 00:00:00 UTC: a calendar label in UTC
    (Finnhub daily epoch, Alpha Vantage relabel) — session date = UTC
    date. Localizing this would shift the day (e.g. to the prior NY
    evening).
  * any other tz-aware stamp: session date = date in the exchange tz
    (Yahoo exchange-midnight stamps land on the correct date; an
    intraday-or-close instant during a session also lies on that
    exchange's session date).

If no exchange tz is known, the canonical instant is the UTC date at
00:00 UTC. Daily bars only; intraday timeframes pass through unchanged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _exchange_zone(exchange_tz: str | None) -> ZoneInfo | None:
    if not exchange_tz:
        return None
    try:
        return ZoneInfo(exchange_tz)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def canonical_session_date(ts: datetime, exchange_tz: str | None) -> date:
    """Return the trading session date a daily stamp describes.

    This is the single attribution rule shared by ingestion, the duplicate
    auditor, and the reconciliation tool. It must stay in lockstep with
    :func:`canonical_daily_timestamp`:

    * naive stamp: the date is already a provider calendar label;
    * exact 00:00:00 UTC: a calendar label in UTC (Finnhub/Twelve Data/
      Alpha Vantage style), so the UTC date is the session date;
    * any other tz-aware stamp: the date in the exchange timezone (Yahoo
      exchange-midnight stamps, intraday/close instants).

    The exact-UTC-midnight branch matters for US exchanges: converting
    2026-10-23T00:00Z to America/New_York yields 2026-10-22, which is the
    previous session and the bug class BAR-002 originally mis-audited.
    """
    if ts.tzinfo is None:
        return ts.date()

    ts_utc = ts.astimezone(UTC)
    if (
        ts_utc.hour == 0
        and ts_utc.minute == 0
        and ts_utc.second == 0
        and ts_utc.microsecond == 0
    ):
        return ts_utc.date()

    tz = _exchange_zone(exchange_tz)
    if tz is not None:
        return ts.astimezone(tz).date()
    return ts_utc.date()


def canonical_daily_timestamp(
    ts: datetime,
    timeframe: str,
    exchange_tz: str | None,
) -> datetime:
    """Return the canonical stored instant for a daily bar."""
    if timeframe != "1d":
        return ts

    tz = _exchange_zone(exchange_tz)
    day = canonical_session_date(ts, exchange_tz)
    if tz is not None:
        return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def canonical_instant_for_session_day(day: date, exchange_tz: str | None) -> datetime:
    """Return the canonical stored instant for a known session date."""
    tz = _exchange_zone(exchange_tz)
    if tz is not None:
        return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
