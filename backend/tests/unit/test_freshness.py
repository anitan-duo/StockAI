"""Unit: freshness engine classification. No network/DB.

Critical regression guard (§30/§31): stale historical data must never be
classified as current market data.
"""

from datetime import UTC, datetime, timedelta

from services.freshness import (
    CLOSED_SESSION_TOLERANCE_S,
    DELAYED_MAX_AGE_S,
    FRESH_MAX_AGE_S,
    RECENT_MAX_AGE_S,
    STALE_MAX_AGE_S,
    Freshness,
    classify_freshness,
    freshness_rank,
    is_presentable_as_current,
)

NOW = datetime(2026, 10, 2, 15, 0, 0, tzinfo=UTC)


def _ago(seconds: float) -> datetime:
    return NOW - timedelta(seconds=seconds)


def test_none_timestamp_is_unavailable():
    assert classify_freshness(None, now=NOW, market_status="open") is Freshness.UNAVAILABLE


def test_future_timestamp_is_unavailable_not_fresh():
    # A timestamp 1 hour in the future is a data-integrity violation.
    future = NOW + timedelta(hours=1)
    assert classify_freshness(future, now=NOW, market_status="open") is Freshness.UNAVAILABLE


def test_small_future_slack_is_tolerated():
    # 2s clock skew must not flag a live quote as unavailable.
    assert classify_freshness(NOW + timedelta(seconds=2), now=NOW, market_status="open") is Freshness.FRESH


def test_open_market_tiers():
    assert classify_freshness(_ago(5), now=NOW, market_status="open") is Freshness.FRESH
    assert classify_freshness(_ago(FRESH_MAX_AGE_S + 1), now=NOW, market_status="open") is Freshness.RECENT
    assert classify_freshness(_ago(RECENT_MAX_AGE_S + 1), now=NOW, market_status="open") is Freshness.DELAYED
    assert classify_freshness(_ago(DELAYED_MAX_AGE_S + 1), now=NOW, market_status="open") is Freshness.STALE


def test_open_market_old_data_is_never_fresh():
    # 2001-era data must classify as STALE, never as current.
    ancient = datetime(2001, 9, 11, tzinfo=UTC)
    assert classify_freshness(ancient, now=NOW, market_status="open") is Freshness.STALE
    assert not is_presentable_as_current(Freshness.STALE)


def test_closed_market_overnight_is_delayed_not_stale():
    # Friday close viewed Monday morning (~64h) is still honest delayed data.
    friday_close = _ago(64 * 3600)
    assert classify_freshness(friday_close, now=NOW, market_status="closed") is Freshness.DELAYED


def test_closed_market_beyond_tolerance_is_stale():
    old = _ago(CLOSED_SESSION_TOLERANCE_S + 3600)
    assert classify_freshness(old, now=NOW, market_status="closed") is Freshness.STALE


def test_unknown_market_status_is_conservative():
    # Unknown status must not inflate freshness.
    assert classify_freshness(_ago(5), now=NOW, market_status=None) is Freshness.RECENT
    assert classify_freshness(_ago(30 * 3600), now=NOW, market_status=None) is Freshness.STALE


def test_ingestion_bound_prevents_fresh_from_old_fetch():
    # Provider timestamp claims "now", but we ingested it 2 hours ago and
    # the session is open: cannot be FRESH.
    assert (
        classify_freshness(
            NOW, now=NOW, ingested_at=NOW - timedelta(hours=2), market_status="open"
        )
        is not Freshness.FRESH
    )


def test_naive_timestamp_is_handled():
    naive = NOW.replace(tzinfo=None) - timedelta(seconds=10)
    assert classify_freshness(naive, now=NOW, market_status="open") is Freshness.FRESH


def test_rank_ordering():
    assert freshness_rank(Freshness.FRESH) < freshness_rank(Freshness.RECENT)
    assert freshness_rank(Freshness.RECENT) < freshness_rank(Freshness.DELAYED)
    assert freshness_rank(Freshness.DELAYED) < freshness_rank(Freshness.STALE)
    assert freshness_rank(Freshness.STALE) < freshness_rank(Freshness.UNAVAILABLE)


def test_presentable_as_current():
    assert is_presentable_as_current(Freshness.FRESH)
    assert is_presentable_as_current(Freshness.RECENT)
    assert is_presentable_as_current(Freshness.DELAYED)
    assert not is_presentable_as_current(Freshness.STALE)
    assert not is_presentable_as_current(Freshness.UNAVAILABLE)


def test_threshold_constants_are_coherent():
    assert 0 < FRESH_MAX_AGE_S < RECENT_MAX_AGE_S < DELAYED_MAX_AGE_S < STALE_MAX_AGE_S
    assert CLOSED_SESSION_TOLERANCE_S > STALE_MAX_AGE_S