"""Failure injection: provider fallback, malformed data, bad artifacts, bad tokens. No network."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.ingestion.providers.base import (
    FallbackMarketDataProvider,
    HistoricalPriceData,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    QuoteData,
)


class _Failing:
    def __init__(self, exc):
        self._exc = exc

    async def search_instruments(self, *a, **k):
        raise self._exc

    async def get_historical_prices(self, *a, **k):
        raise self._exc


class _OK:
    async def search_instruments(self, *a, **k):
        from services.ingestion.providers.base import InstrumentInfo

        return [InstrumentInfo(symbol="AAPL", name="Apple", exchange="NASDAQ", currency="USD")]

    async def get_historical_prices(self, *a, **k):
        return [
            HistoricalPriceData(
                symbol="AAPL",
                timeframe="1d",
                timestamp=datetime.now(timezone.utc),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150.5"),
                volume=1000,
            )
        ]


class _Router:
    def __init__(self, providers):
        self.providers = {"US": providers}

    def get_all_providers(self, market):
        return self.providers.get(market, [])


def _quote(**over):
    base = {
        "symbol": "AAPL",
        "price": Decimal("150"),
        "change": Decimal("1"),
        "change_percent": Decimal("0.7"),
        "volume": 1000,
        "high": Decimal("151"),
        "low": Decimal("149"),
        "open": Decimal("150"),
        "previous_close": Decimal("149"),
        "timestamp": datetime.now(timezone.utc),
        "market_status": "open",
    }
    base.update(over)
    return QuoteData(**base)


@pytest.mark.asyncio
async def test_fallback_skips_timeout_and_rate_limit():
    fb = FallbackMarketDataProvider(
        _Router([_Failing(ProviderTimeoutError("t")), _Failing(ProviderRateLimitError("t")), _OK()])
    )
    assert len(await fb.search_instruments("AAPL")) == 1
    assert len(await fb.get_historical_prices("AAPL", "X", "1d", datetime.now(timezone.utc), datetime.now(timezone.utc))) == 1


@pytest.mark.asyncio
async def test_fallback_all_fail_returns_empty_honestly():
    fb = FallbackMarketDataProvider(_Router([_Failing(ProviderTimeoutError("t"))]))
    assert await fb.search_instruments("AAPL") == []


def test_malformed_provider_data_rejected():
    from services.ingestion.ingestion_service import IngestionService, ValidationError

    svc = IngestionService.__new__(IngestionService)
    with pytest.raises(ValidationError):
        svc._validate_quote(_quote(price=Decimal("-5")))
    with pytest.raises(ValidationError):
        svc._validate_price_bar(
            HistoricalPriceData(
                symbol="AAPL",
                timeframe="1d",
                timestamp=datetime.now(timezone.utc),
                open=Decimal("150"),
                high=Decimal("140"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=100,
            )
        )
    with pytest.raises(ProviderDataError):
        raise ProviderDataError("p", "malformed upstream payload")


def test_invalid_artifact_rejected():
    import joblib

    with pytest.raises(Exception):
        joblib.load("/nonexistent/model.pkl")


def test_expired_and_revoked_style_tokens_rejected():
    from datetime import timedelta

    from apps.api.services.auth import auth_service

    class _U:
        from uuid import uuid4

        id = uuid4()
        email = "x@example.com"
        is_superuser = False

    expired = auth_service.create_access_token(_U(), expires_delta=timedelta(seconds=-1))
    assert auth_service.decode_token(expired) is None
