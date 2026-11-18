"""Regression: /health/freshness must catch per-market stalls.

The EU/IN ingestion stalled 10 days while US bars kept the GLOBAL max
fresh, so `stale` stayed false. Freshness is now per-market."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


async def _seed_markets_with_bars(db_session):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.price import PriceBar

    now = datetime.now(UTC)
    from datetime import time

    fresh_market = Market(
        code="US", name="United States", country_code="USA", currency="USD",
        timezone="America/New_York", market_open=time(9, 30), market_close=time(16, 0),
    )
    stale_market = Market(
        code="EU", name="Europe", country_code="DEU", currency="EUR",
        timezone="Europe/Berlin", market_open=time(9, 0), market_close=time(17, 30),
    )
    db_session.add_all([fresh_market, stale_market])
    await db_session.flush()
    fresh_ex = Exchange(code="NASDAQ", name="NASDAQ", market_id=fresh_market.id, timezone="America/New_York", currency="USD", market_open=time(9, 30), market_close=time(16, 0))
    stale_ex = Exchange(code="XETRA", name="XETRA", market_id=stale_market.id, timezone="Europe/Berlin", currency="EUR", market_open=time(9, 0), market_close=time(17, 30))
    db_session.add_all([fresh_ex, stale_ex])
    await db_session.flush()
    fresh_i = Instrument(symbol="AAPL", name="Apple", exchange_id=fresh_ex.id, currency="USD")
    stale_i = Instrument(symbol="SAP", name="SAP", exchange_id=stale_ex.id, currency="EUR")
    db_session.add_all([fresh_i, stale_i])
    await db_session.flush()
    db_session.add(PriceBar(instrument_id=fresh_i.id, timeframe="1d", timestamp=now - timedelta(hours=4), open=1, high=1, low=1, close=1, volume=1))
    db_session.add(PriceBar(instrument_id=stale_i.id, timeframe="1d", timestamp=now - timedelta(days=10), open=1, high=1, low=1, close=1, volume=1))
    await db_session.commit()


@pytest.mark.asyncio
async def test_freshness_reports_per_market_stall(db_session):
    from apps.api.routes.health import freshness_check

    await _seed_markets_with_bars(db_session)
    out = await freshness_check(session=db_session)

    assert out["markets"]["US"]["stale"] is False
    assert out["markets"]["EU"]["stale"] is True
    # Overall stale must surface the EU stall (global max alone hid it).
    assert out["stale"] is True
