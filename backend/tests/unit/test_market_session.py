"""Unit tests for the market-session engine (services/market_session.py)."""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from types import SimpleNamespace

from services.market_session import (
    derive_market_status,
    refine_source_timestamp,
    session_bounds,
)


@dataclass(frozen=True)
class FakeMarket:
    timezone: str
    market_open: time
    market_close: time
    pre_market_open: time | None = None
    post_market_close: time | None = None


# US-equivalent hours in America/New_York: 09:30-16:00, pre 04:00, post 20:00.
US_MARKET = FakeMarket(
    timezone="America/New_York",
    market_open=time(9, 30),
    market_close=time(16, 0),
    pre_market_open=time(4, 0),
    post_market_close=time(20, 0),
)


def _ny(dt: datetime) -> datetime:
    """Interpret a naive datetime as New York local and return aware UTC."""
    from zoneinfo import ZoneInfo

    return dt.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


class TestDeriveMarketStatus:
    def test_regular_session_is_open(self):
        # Wednesday 2026-09-30, 12:00 NY == 16:00 UTC.
        now = _ny(datetime(2026, 9, 30, 12, 0))
        assert derive_market_status(US_MARKET, now=now) == "open"

    def test_before_regular_session_with_pre_market(self):
        now = _ny(datetime(2026, 9, 30, 6, 0))
        assert derive_market_status(US_MARKET, now=now) == "pre-market"

    def test_before_pre_market_is_closed(self):
        now = _ny(datetime(2026, 9, 30, 2, 0))
        assert derive_market_status(US_MARKET, now=now) == "closed"

    def test_after_close_within_post_market(self):
        now = _ny(datetime(2026, 9, 30, 17, 30))
        assert derive_market_status(US_MARKET, now=now) == "after-hours"

    def test_after_post_market_is_closed(self):
        now = _ny(datetime(2026, 9, 30, 21, 0))
        assert derive_market_status(US_MARKET, now=now) == "closed"

    def test_weekend_is_closed_even_during_session_hours(self):
        # Saturday 2026-10-03, 12:00 NY.
        now = _ny(datetime(2026, 10, 3, 12, 0))
        assert derive_market_status(US_MARKET, now=now) == "closed"

    def test_sunday_is_closed(self):
        now = _ny(datetime(2026, 10, 4, 12, 0))
        assert derive_market_status(US_MARKET, now=now) == "closed"

    def test_without_pre_post_bounds_only_regular_session(self):
        m = FakeMarket(
            timezone="UTC",
            market_open=time(9, 0),
            market_close=time(17, 0),
        )
        assert derive_market_status(m, now=datetime(2026, 10, 5, 8, 0, tzinfo=UTC)) == "closed"
        assert derive_market_status(m, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC)) == "open"
        assert derive_market_status(m, now=datetime(2026, 10, 5, 17, 0, tzinfo=UTC)) == "closed"

    def test_session_bounds_are_utc(self):
        b = session_bounds(US_MARKET, local_date=datetime(2026, 9, 30).date())
        # 09:30 NY == 13:30 UTC on this date (EDT, UTC-4).
        assert b.regular_open_utc == datetime(2026, 9, 30, 13, 30, tzinfo=UTC)
        assert b.regular_close_utc == datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
        assert b.pre_open_utc == datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
        assert b.post_close_utc == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


class TestRefineSourceTimestamp:
    def test_non_date_only_metadata_is_untouched(self):
        ts = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
        out, refined = refine_source_timestamp(ts, US_MARKET, metadata={})
        assert out == ts and refined is False

    def test_prior_trading_day_stays_midnight(self):
        # Source: Friday's trading day, fetched Sunday 12:00 UTC.
        ts = datetime(2026, 10, 2, tzinfo=UTC)
        out, refined = refine_source_timestamp(
            ts, US_MARKET, metadata={"source_date_only": True},
            now=datetime(2026, 10, 4, 12, 0, tzinfo=UTC),
        )
        assert out == ts and refined is False

    def test_same_trading_day_clamps_to_session_open(self):
        # Source: Wednesday date-only claim fetched 15:00 UTC same NY day.
        ts = datetime(2026, 9, 30, 4, 0, tzinfo=UTC)
        out, refined = refine_source_timestamp(
            ts, US_MARKET, metadata={"source_date_only": True},
            now=datetime(2026, 9, 30, 15, 0, tzinfo=UTC),
        )
        assert refined is True
        # Session open for that NY day is 13:30 UTC.
        assert out == datetime(2026, 9, 30, 13, 30, tzinfo=UTC)

    def test_never_produces_future_timestamp(self):
        # A malformed same-day claim at 00:30 UTC — the session has not
        # opened yet (opens 13:30 UTC); the raw date must be kept rather
        # than clamped to a future instant.
        ts = datetime(2026, 10, 5, 0, 30, tzinfo=UTC)  # Monday
        out, refined = refine_source_timestamp(
            ts, US_MARKET, metadata={"source_date_only": True},
            now=datetime(2026, 10, 5, 0, 30, tzinfo=UTC),
        )
        assert out == ts


def test_simple_namespace_market_works():
    """The helpers duck-type the ORM Market row."""
    m = SimpleNamespace(
        timezone="Europe/Berlin",
        market_open=time(9, 0),
        market_close=time(17, 30),
        pre_market_open=None,
        post_market_close=None,
    )
    # Monday 2026-10-05 10:00 Berlin == 08:00 UTC: open.
    assert derive_market_status(m, now=datetime(2026, 10, 5, 8, 0, tzinfo=UTC)) == "open"
