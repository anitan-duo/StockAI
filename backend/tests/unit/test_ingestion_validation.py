"""Unit: ingestion validation (OHLC, positivity, staleness). No network/DB."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.ingestion.ingestion_service import IngestionService, ValidationError
from services.ingestion.providers.base import HistoricalPriceData, QuoteData


def _quote(**over):
    base = {
        "symbol": "AAPL",
        "price": Decimal("150"),
        "change": Decimal("1"),
        "change_percent": Decimal("0.7"),
        "volume": 1_000_000,
        "high": Decimal("151"),
        "low": Decimal("149"),
        "open": Decimal("150"),
        "previous_close": Decimal("149"),
        "timestamp": datetime.now(timezone.utc),
        "market_status": "open",
    }
    base.update(over)
    return QuoteData(**base)


def _bar(**over):
    base = {
        "symbol": "AAPL",
        "timeframe": "1d",
        "timestamp": datetime.now(timezone.utc),
        "open": Decimal("150"),
        "high": Decimal("151"),
        "low": Decimal("149"),
        "close": Decimal("150.5"),
        "volume": 1_000_000,
    }
    base.update(over)
    return HistoricalPriceData(**base)


def test_valid_quote_and_bar_pass():
    svc = IngestionService.__new__(IngestionService)
    svc._validate_quote(_quote())
    svc._validate_price_bar(_bar())


def test_quote_rejects_nonpositive_price():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_quote(_quote(price=Decimal("0")))


def test_quote_rejects_bad_high_low():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_quote(_quote(high=Decimal("140")))
    with pytest.raises(ValidationError):
        svc._validate_quote(_quote(low=Decimal("160")))


def test_quote_rejects_stale():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_quote(
            _quote(timestamp=datetime.now(timezone.utc) - timedelta(hours=25))
        )


def test_bar_rejects_nonpositive_and_bad_range():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(open=Decimal("-1")))
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(high=Decimal("140")))
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(low=Decimal("160")))
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(volume=-5))


def test_bar_rejects_zero_volume_no_session_bars():
    """Oct 2026: 60 zero-volume holiday/weekend stubs poisoned trailing
    volume features (vol_price_corr NaN -> inference fail-closed for weeks).
    Zero reported volume = no session evidence, rejected at the door."""
    svc = IngestionService.__new__(IngestionService)
    # Flat holiday stub.
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(volume=0, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100")))
    # Zero volume WITH a range is equally session-less (Oct 5-9 2026 IN/EU).
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(volume=0, open=Decimal("100"), high=Decimal("102"), low=Decimal("99"), close=Decimal("101")))
    # Thin but real sessions still accepted.
    svc._validate_price_bar(_bar(volume=1))


def test_bar_rejects_impossible_intraday_range():
    """INFY 2026-10-07: open 10.41 vs high 1009.00 (unit error) passed OHLC
    checks. A >5x spread inside one session is never real volatility."""
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_price_bar(_bar(open=Decimal("10.41"), high=Decimal("1009"), low=Decimal("10.37"), close=Decimal("10.55"), volume=1000))
    # Normal volatility passes (and the boundary itself passes).
    svc._validate_price_bar(_bar(open=Decimal("100"), high=Decimal("104"), low=Decimal("99"), close=Decimal("103"), volume=1000))


def test_quote_rejects_impossible_intraday_range():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_quote(
            _quote(open=Decimal("10.41"), high=Decimal("1009"), low=Decimal("10.37"), price=Decimal("10.55"), volume=1000)
        )


# --- BAR-002: canonical daily session-day stamping ---

from datetime import UTC, date  # noqa: E402

from services.ingestion.canonical_days import (  # noqa: E402
    canonical_daily_timestamp,
    canonical_instant_for_session_day,
    canonical_session_date,
)


def test_canonical_ny_session_stamps_to_new_york_midnight_in_utc():
    # EDT (summer): NY midnight = 04:00 UTC; EST (winter): 05:00 UTC.
    assert canonical_daily_timestamp(
        datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc), "1d", "America/New_York"
    ) == datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    assert canonical_daily_timestamp(
        datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc), "1d", "America/New_York"
    ) == datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)


def test_canonical_utc_midnight_calendar_labels_keep_session_date():
    # Finnhub epoch UTC-midnight: session date = UTC date, NOT shifted back.
    assert canonical_daily_timestamp(
        datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc), "1d", "America/New_York"
    ) == datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)


def test_canonical_ist_session_maps_to_ist_midnight():
    # IST midnight = 18:30 UTC of the previous UTC day; Yahoo IST bars land there.
    assert canonical_daily_timestamp(
        datetime(2026, 7, 14, 18, 30, tzinfo=timezone.utc), "1d", "Asia/Kolkata"
    ) == datetime(2026, 7, 14, 18, 30, tzinfo=timezone.utc)


def test_canonical_naive_calendar_dates_pass_through():
    naive = datetime(2026, 7, 15, 0, 0)
    assert canonical_daily_timestamp(naive, "1d", "America/New_York") == datetime(
        2026, 7, 15, 4, 0, tzinfo=timezone.utc
    )
    assert canonical_daily_timestamp(naive, "1d", None) == datetime(
        2026, 7, 15, 0, 0, tzinfo=timezone.utc
    )


def test_canonical_cet_session():
    # CEST (summer): CET midnight = 22:00 UTC prev day; CET (winter): 23:00 UTC.
    assert canonical_daily_timestamp(
        datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc), "1d", "Europe/Paris"
    ) == datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)
    assert canonical_daily_timestamp(
        datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc), "1d", "Europe/Paris"
    ) == datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)


def test_canonical_unknown_timezone_falls_back_to_utc_midnight():
    assert canonical_daily_timestamp(
        datetime(2026, 7, 15, 13, 45, tzinfo=timezone.utc), "1d", "Not/AZone"
    ) == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    assert canonical_daily_timestamp(
        datetime(2026, 7, 15, 13, 45, tzinfo=timezone.utc), "1d", None
    ) == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)


def test_canonical_intraday_passes_through_unchanged():
    ts = datetime(2026, 7, 15, 13, 45, tzinfo=timezone.utc)
    assert canonical_daily_timestamp(ts, "1h", "America/New_York") is ts


def test_provider_stamps_for_same_session_converge():
    """The BAR-002 contract: every provider's stamp for one session maps to
    ONE instant, regardless of provider convention."""
    session_ny = "America/New_York"
    finnhub = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)   # UTC-midnight label
    alpha = datetime(2026, 7, 15, 0, 0)                           # naive calendar label
    yahoo = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)      # NY midnight in UTC (EDT)
    a = canonical_daily_timestamp(finnhub, "1d", session_ny)
    b = canonical_daily_timestamp(alpha, "1d", session_ny)
    c = canonical_daily_timestamp(yahoo, "1d", session_ny)
    assert a == b == c == yahoo


def test_session_date_utc_midnight_is_not_previous_us_session():
    """Regression for the flawed BAR-002 audit: a 00:00Z label on Oct 23
    describes the Oct 23 session, not Oct 22 (which conversion to New York
    local time would yield)."""
    label = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
    yahoo = datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc)
    assert canonical_session_date(label, "America/New_York") == date(2026, 10, 23)
    assert canonical_session_date(yahoo, "America/New_York") == date(2026, 10, 23)
    assert canonical_daily_timestamp(label, "1d", "America/New_York") == yahoo
    assert canonical_session_date(
        datetime(2026, 10, 22, 4, 0, tzinfo=timezone.utc), "America/New_York"
    ) == date(2026, 10, 22)


def test_session_date_positive_offset_exchanges():
    ist_label = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    ist_midnight = datetime(2026, 8, 19, 18, 30, tzinfo=timezone.utc)
    cet_label = datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc)
    cet_midnight = datetime(2026, 10, 28, 23, 0, tzinfo=timezone.utc)
    assert canonical_session_date(ist_label, "Asia/Kolkata") == date(2026, 8, 20)
    assert canonical_session_date(ist_midnight, "Asia/Kolkata") == date(2026, 8, 20)
    assert canonical_session_date(cet_label, "Europe/Paris") == date(2026, 10, 29)
    assert canonical_session_date(cet_midnight, "Europe/Paris") == date(2026, 10, 29)


def test_session_instant_round_trip_across_dst():
    for day, tz, expected in [
        (date(2026, 7, 15), "America/New_York", datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)),
        (date(2026, 1, 15), "America/New_York", datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)),
        (date(2026, 7, 15), "Europe/Paris", datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)),
        (date(2026, 1, 15), "Europe/Paris", datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)),
    ]:
        instant = canonical_instant_for_session_day(day, tz)
        assert instant == expected
        assert canonical_session_date(instant, tz) == day
        assert canonical_daily_timestamp(instant, "1d", tz) == instant
