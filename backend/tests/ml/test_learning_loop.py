"""Learning-loop monitor: confirmed outcomes only, calibration, no auto-promotion."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest

from services.mlops.monitor import compute_monitor_snapshot


async def _seed(session, outcomes: int, correct: int, confidence: float = 0.8):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import (
        Model,
        ModelVersion,
        Prediction,
        PredictionOutcome,
    )

    now = datetime.now(UTC)
    market = Market(
        code="US",
        name="United States",
        country_code="USA",
        currency="USD",
        timezone="America/New_York",
        market_open=time(9, 30),
        market_close=time(16, 0),
    )
    session.add(market)
    await session.flush()
    exchange = Exchange(
        code="NASDAQ",
        name="NASDAQ",
        market_id=market.id,
        timezone="America/New_York",
        currency="USD",
        market_open=time(9, 30),
        market_close=time(16, 0),
    )
    session.add(exchange)
    await session.flush()
    instrument = Instrument(
        symbol="AAPL",
        name="Apple",
        exchange_id=exchange.id,
        currency="USD",
    )
    session.add(instrument)
    await session.flush()
    model = Model(name="Ensemble", model_type="ensemble")
    session.add(model)
    await session.flush()
    version = ModelVersion(
        model_id=model.id,
        version="real-v1.0",
        is_active=True,
        training_date=now - timedelta(days=90),
        metrics={},
        hyperparameters={},
    )
    session.add(version)
    await session.flush()

    for i in range(outcomes):
        pred = Prediction(
            instrument_id=instrument.id,
            model_version_id=version.id,
            horizon="1d",
            predicted_direction="up",
            up_probability=Decimal(str(confidence)),
            neutral_probability=Decimal(str(round((1 - confidence) / 2, 4))),
            down_probability=Decimal(str(round((1 - confidence) / 2, 4))),
            expected_return=Decimal("0.01"),
            range_lower=Decimal("-0.02"),
            range_upper=Decimal("0.03"),
            confidence=int(confidence * 100),
            # Distinct days: each prediction is one forecast per bar day
            # (bar-day dedupe collapses same-day duplicate runs).
            prediction_timestamp=now - timedelta(days=2 + i, hours=1),
            data_timestamp=now - timedelta(days=2 + i, hours=1),
            features_snapshot={
                "high_vol_regime": 1.0 if i % 2 == 0 else 0.0,
                "uptrend_regime": 1.0,
            },
        )
        session.add(pred)
        await session.flush()
        session.add(
            PredictionOutcome(
                prediction_id=pred.id,
                actual_return=Decimal("1.0") if i < correct else Decimal("-0.2"),
                actual_direction="up" if i < correct else "neutral",
                is_correct=i < correct,
                evaluation_price=Decimal("101"),
                evaluation_timestamp=now - timedelta(days=1 + i, hours=1),
                evaluated_at=now - timedelta(hours=1, minutes=i),
                source="test",
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_empty_monitor_fabricates_nothing(db_session):
    snap = await compute_monitor_snapshot(db_session)
    assert snap["confirmed"]["n_matured_30d"] == 0
    assert "accuracy_30d" not in snap["confirmed"]
    assert snap["learning"]["state"] == "collecting"
    assert snap["learning"]["automatic_promotion"] is False
    assert snap["provisional"]["predictions_pending_outcome"] == 0
    assert snap["drift"][0]["metric"] == "sample_size"


@pytest.mark.asyncio
async def test_confirmed_calibration_and_version_breakdown(db_session):
    await _seed(db_session, outcomes=40, correct=30, confidence=0.8)
    snap = await compute_monitor_snapshot(db_session)
    confirmed = snap["confirmed"]
    assert confirmed["n_matured_30d"] == 40
    assert confirmed["accuracy_30d"] == pytest.approx(0.75)
    assert confirmed["by_model_version"]["real-v1.0"]["n"] == 40
    cal = confirmed["calibration_30d"]
    assert sum(b["n"] for b in cal["bins"]) == 40
    assert confirmed["ece_30d"] == pytest.approx(
        sum(
            (b["n"] / 40) * abs(b["observed_accuracy"] - b["mean_confidence"])
            for b in cal["bins"]
            if b["n"]
        ),
        abs=1e-4,
    )
    assert confirmed["by_regime"]["high_volatility"]["on"]["n"] == 20
    assert confirmed["by_regime"]["uptrend_50_200"]["on"]["n"] == 40
    assert confirmed["recent_7d"]["n"] == 40
    assert snap["learning"]["state"] in {"monitoring", "calibration_review"}


@pytest.mark.asyncio
async def test_calibration_drift_is_confirmed_and_deduped(db_session):
    await _seed(db_session, outcomes=40, correct=40, confidence=0.5)
    first = await compute_monitor_snapshot(db_session)
    assert any(a["metric"] == "ece_30d" for a in first["drift"])
    second = await compute_monitor_snapshot(db_session)

    from sqlalchemy import func, select

    from apps.api.models.mlops import DriftObservation

    count = (
        await db_session.execute(
            select(func.count(DriftObservation.id)).where(
                DriftObservation.metric == "ece_30d",
                DriftObservation.acknowledged.is_(False),
            )
        )
    ).scalar()
    assert count == 1
    assert second["learning"]["automatic_retraining"] is False


@pytest.mark.asyncio
async def test_analytics_workspace_uses_confirmed_outcomes_only(db_session):
    from services.mlops.analytics import compute_performance_analytics

    await _seed(db_session, outcomes=40, correct=30, confidence=0.8)
    result = await compute_performance_analytics(db_session, days=90)
    assert result["scope"]["confirmed_only"] is True
    assert result["summary"]["n"] == 40
    assert result["summary"]["accuracy"] == pytest.approx(0.75)
    assert result["by_symbol"]["AAPL:NASDAQ"]["n"] == 40
    assert result["by_version"]["real-v1.0"]["n"] == 40
    assert result["calibration"]["n"] == 40
    assert sum(b["n"] for b in result["calibration"]["bins"]) == 40
    assert result["recent_outcomes"][0]["symbol"] == "AAPL"
    assert result["caveats"]

    empty = await compute_performance_analytics(db_session, days=90, symbol="MSFT")
    assert empty["summary"]["n"] == 0
    assert empty["summary"]["accuracy"] is None
    assert empty["calibration"]["bins"] == []


def test_analytics_route_is_registered_and_auth_gated(db_session):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routes.auth import get_current_user

    client = TestClient(app)
    unauthenticated = client.get("/api/v1/analytics/performance")
    assert unauthenticated.status_code in (401, 403)

    app.dependency_overrides[get_current_user] = lambda: {"email": "analyst@example.com"}
    try:
        response = client.get("/api/v1/analytics/performance?days=90")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    body = response.json()
    assert body["scope"]["confirmed_only"] is True
    assert body["summary"]["n"] == 0
