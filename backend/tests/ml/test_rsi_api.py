"""RSI endpoint contract tests (repositories stubbed; no live DB required)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient


class FakeBar:
    def __init__(self, timestamp: datetime, close: float):
        self.timestamp = timestamp
        self.close = close


def _bars(n: int = 90) -> list[FakeBar]:
    start = datetime(2024, 1, 1)
    close = 100 + np.cumsum(np.random.RandomState(5).randn(n) * 0.4)
    return [FakeBar(start + timedelta(days=i), float(close[i])) for i in range(n)]


@pytest.fixture()
def client(monkeypatch):
    from apps.api.main import app
    from apps.api.repositories import market
    from apps.api.repositories.prediction import PredictionRepository

    async def fake_exchange(self, code):
        return SimpleNamespace(id="ex-1", code=code) if code.upper() == "NASDAQ" else None

    async def fake_instrument(self, symbol, exchange_id):
        return SimpleNamespace(id="inst-1", symbol=symbol) if symbol == "AAPL" else None

    async def fake_latest(self, instrument_id, timeframe="1d", limit=1):
        return list(reversed(_bars()))[:limit]

    async def no_prediction(self, instrument_id, horizon):
        return None

    monkeypatch.setattr(market.ExchangeRepository, "get_by_code", fake_exchange)
    monkeypatch.setattr(market.InstrumentRepository, "get_by_symbol_exchange", fake_instrument)
    monkeypatch.setattr(market.PriceBarRepository, "get_latest", fake_latest)
    monkeypatch.setattr(PredictionRepository, "get_latest_for_instrument", no_prediction)
    return TestClient(app)


def test_rsi_endpoint_returns_point_in_time_analysis(client):
    r = client.get("/api/v1/predictions/stocks/AAPL/rsi?exchange=NASDAQ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["exchange"] == "NASDAQ"
    assert body["bar_count"] == 90
    assert 0 <= body["current"]["rsi_14"] <= 100
    assert body["prediction_direction"] is None
    assert body["agreement"]["status"] == "unknown"
    assert len(body["series"]) == 90
    assert body["series"][-1]["timestamp"].startswith("2024-03-30")


def test_rsi_endpoint_refuses_insufficient_history(client, monkeypatch):
    from apps.api.repositories import market

    async def short_latest(self, instrument_id, timeframe="1d", limit=1):
        return list(reversed(_bars(20)))[:limit]

    monkeypatch.setattr(market.PriceBarRepository, "get_latest", short_latest)
    r = client.get("/api/v1/predictions/stocks/AAPL/rsi?exchange=NASDAQ")
    assert r.status_code == 503
    assert r.json()["detail"]["status"] == "UNAVAILABLE"


def test_rsi_endpoint_unknown_exchange(client):
    r = client.get("/api/v1/predictions/stocks/AAPL/rsi?exchange=NYSE")
    assert r.status_code == 404
