"""Regression: rerunning inference on the same closed bar must not duplicate rows.

Duplicate predictions were a hit-rate corruption vector: each duplicate got
its own outcome, so a single trading day could be counted N times in the
denominator.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select


async def _seed(db_session):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import Model, ModelVersion

    market = Market(
        code="US",
        name="United States",
        country_code="USA",
        currency="USD",
        timezone="America/New_York",
        market_open=time(9, 30),
        market_close=time(16, 0),
    )
    db_session.add(market)
    await db_session.flush()
    exchange = Exchange(
        code="NASDAQ",
        name="NASDAQ",
        market_id=market.id,
        timezone="America/New_York",
        currency="USD",
        market_open=time(9, 30),
        market_close=time(16, 0),
    )
    db_session.add(exchange)
    await db_session.flush()
    instrument = Instrument(
        symbol="AAPL", name="Apple", exchange_id=exchange.id, currency="USD"
    )
    model = Model(name="Ensemble", model_type="ensemble")
    db_session.add_all([instrument, model])
    await db_session.flush()
    version = ModelVersion(
        model_id=model.id,
        version="real-v1.0",
        is_active=True,
        metrics={},
        hyperparameters={},
    )
    db_session.add(version)
    await db_session.flush()
    return instrument, version


@pytest.mark.asyncio
async def test_same_bar_inference_is_idempotent(db_session, monkeypatch):
    from apps.api.models.prediction import Prediction
    from services.prediction.prediction_service import PredictionEngine, PredictionService

    instrument, version = await _seed(db_session)
    bar_ts = datetime(2026, 6, 8, 20, 0, tzinfo=UTC)
    calls = {"n": 0}

    async def fake_infer(self, instrument_id, model_version_id, horizon, features, artifact_override=None):
        calls["n"] += 1
        return {
            "predicted_direction": "up",
            "up_probability": Decimal("0.4200"),
            "neutral_probability": Decimal("0.3100"),
            "down_probability": Decimal("0.2700"),
            "expected_return": Decimal("0.0100"),
            "range_lower": Decimal("-0.0100"),
            "range_upper": Decimal("0.0300"),
            "confidence": 62,
            "_feature_dict": {"price": 190.0, "rsi_14": 55.0, "marker": calls["n"]},
            "_data_timestamp": bar_ts,
            "_prob_max": 0.42,
            "_no_edge": False,
        }

    monkeypatch.setattr(
        PredictionEngine, "generate_prediction_async", fake_infer, raising=False
    )

    svc = PredictionService(db_session)
    first = await svc.generate_prediction(instrument.id, "1d", version.id)
    await db_session.commit()
    second = await svc.generate_prediction(instrument.id, "1d", version.id)
    await db_session.commit()

    assert calls["n"] == 2  # inference may rerun...
    assert first.id == second.id  # ...but persistence must not duplicate
    count = (
        await db_session.execute(select(func.count(Prediction.id)))
    ).scalar_one()
    assert count == 1

    # Data timestamp is the bar timestamp, not wall-clock now (PIT).
    assert first.data_timestamp.replace(tzinfo=UTC) == bar_ts
    assert first.prediction_timestamp.replace(tzinfo=UTC) == bar_ts
