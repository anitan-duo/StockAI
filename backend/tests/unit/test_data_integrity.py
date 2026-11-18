"""Data-integrity regression tests (no network/DB).

Critical invariant: a stale historical dataset must never be silently
presented as current market data.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.freshness import (
    Freshness,
    classify_freshness,
    is_presentable_as_current,
)
from services.ingestion.ingestion_service import IngestionService, ValidationError
from services.ingestion.providers.base import HistoricalPriceData
from services.ingestion.providers.factory import normalize_market_code


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


def test_ancient_bar_is_valid_but_never_presentable():
    """2001-era bars are valid *history* but must classify STALE, never current."""
    svc = IngestionService.__new__(IngestionService)
    ancient = _bar(timestamp=datetime(2001, 9, 11, tzinfo=timezone.utc))
    svc._validate_price_bar(ancient)  # must not raise: history is history
    fresh = classify_freshness(ancient.timestamp, market_status="closed")
    assert fresh == Freshness.STALE
    assert not is_presentable_as_current(fresh)


def test_future_bar_rejected():
    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_price_bar(
            _bar(timestamp=datetime.now(timezone.utc) + timedelta(hours=2))
        )


def test_future_quote_unavailable_not_live():
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert classify_freshness(future, market_status="open") == Freshness.UNAVAILABLE


def test_market_code_aliases_resolve():
    assert normalize_market_code("IN") == "India"
    assert normalize_market_code("in") == "India"
    assert normalize_market_code("EU") == "Europe"
    assert normalize_market_code("europe") == "Europe"
    assert normalize_market_code("US") == "US"
    assert normalize_market_code(None) is None


def test_router_alias_lookup():
    from services.ingestion.providers.base import ProviderRouter
    from services.ingestion.providers.yahoo import YahooFinanceProvider

    r = ProviderRouter()
    r.register_provider("India", YahooFinanceProvider(rate_limit=100), priority=0)
    # DB code IN must still find the India-registered provider.
    assert len(r.get_all_providers("IN")) == 1
    assert len(r.get_all_providers("India")) == 1
    assert len(r.get_all_providers("EU")) == 0
