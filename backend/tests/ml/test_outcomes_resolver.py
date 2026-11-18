"""Regression: the outcome resolver must actually resolve matured predictions.

Catches the P0 defect where every resolution attempt failed with
"'str' object has no attribute 'quantize'" and the per-row error
isolation silently swallowed it (resolved=0 forever).
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal


async def _seed_matured(db_session, *, base: str, nxt: str):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import Model, ModelVersion, Prediction
    from apps.api.models.price import PriceBar

    now = datetime.now(UTC)
    market = Market(
        code="US", name="United States", country_code="USA", currency="USD",
        timezone="America/New_York", market_open=time(9, 30), market_close=time(16, 0),
    )
    db_session.add(market)
    await db_session.flush()
    exchange = Exchange(
        code="NASDAQ", name="NASDAQ", market_id=market.id,
        timezone="America/New_York", currency="USD",
        market_open=time(9, 30), market_close=time(16, 0),
    )
    db_session.add(exchange)
    await db_session.flush()
    instrument = Instrument(symbol="MSFT", name="Microsoft", exchange_id=exchange.id, currency="USD")
    model = Model(name="Ensemble", model_type="ensemble")
    db_session.add_all([instrument, model])
    await db_session.flush()
    version = ModelVersion(model_id=model.id, version="real-v1.0", is_active=True, metrics={}, hyperparameters={})
    db_session.add(version)
    await db_session.flush()

    base_ts = now - timedelta(days=5)
    nxt_ts = base_ts + timedelta(days=1)
    db_session.add(
        PriceBar(
            instrument_id=instrument.id,
            timeframe="1d",
            timestamp=base_ts,
            open=Decimal(base), high=Decimal(base), low=Decimal(base),
            close=Decimal(base), volume=1000,
        )
    )
    db_session.add(
        PriceBar(
            instrument_id=instrument.id,
            timeframe="1d",
            timestamp=nxt_ts,
            open=Decimal(nxt), high=Decimal(nxt), low=Decimal(nxt),
            close=Decimal(nxt), volume=1000,
        )
    )
    db_session.add(
        Prediction(
            instrument_id=instrument.id,
            model_version_id=version.id,
            horizon="1d",
            predicted_direction="up",
            up_probability=Decimal("0.5"),
            neutral_probability=Decimal("0.3"),
            down_probability=Decimal("0.2"),
            expected_return=Decimal("1"),
            range_lower=Decimal("-0.02"),
            range_upper=Decimal("0.02"),
            confidence=55,
            prediction_timestamp=base_ts,
            data_timestamp=base_ts,
            features_snapshot={"price": float(base)},
        )
    )
    await db_session.commit()
    return instrument.id


async def test_resolver_resolves_matured_prediction(db_session):
    from apps.api.models.prediction import Prediction, PredictionOutcome
    from sqlalchemy import select

    from services.prediction.outcomes import resolve_matured_outcomes

    instrument_id = await _seed_matured(db_session, base="100", nxt="102")

    result = await resolve_matured_outcomes(db_session, limit=50)
    assert result["errors"] == [], f"resolver must not error: {result['errors']}"
    assert result["resolved"] == 1
    assert result["skipped_immature"] == 0

    pred = (
        await db_session.execute(select(Prediction).where(Prediction.instrument_id == instrument_id))
    ).scalar_one()
    outcome = (
        await db_session.execute(select(PredictionOutcome).where(PredictionOutcome.prediction_id == pred.id))
    ).scalar_one()
    assert float(outcome.actual_return) == 2.0  # (102-100)/100 * 100
    assert outcome.actual_direction == "up"

    # Idempotent: rerun resolves nothing new.
    rerun = await resolve_matured_outcomes(db_session, limit=50)
    assert rerun["resolved"] == 0


async def test_resolver_reports_and_swallows_no_exceptions(db_session):
    """A resolver run on an empty DB is a clean no-op, never an error."""
    from services.prediction.outcomes import resolve_matured_outcomes

    result = await resolve_matured_outcomes(db_session, limit=50)
    assert result["resolved"] == 0
    assert result["errors"] == []
