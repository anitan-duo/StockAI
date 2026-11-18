"""Regression: neutral predictions must not inflate the analytics hit rate."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest


async def _seed(db_session, groups: list[tuple[str, str, int]]):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import (
        Model,
        ModelVersion,
        Prediction,
        PredictionOutcome,
    )

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
    instrument = Instrument(
        symbol="AAPL", name="Apple", exchange_id=exchange.id, currency="USD"
    )
    model = Model(name="Ensemble", model_type="ensemble")
    db_session.add_all([instrument, model])
    await db_session.flush()
    version = ModelVersion(
        model_id=model.id, version="real-v1.0", is_active=True,
        metrics={}, hyperparameters={},
    )
    db_session.add(version)
    await db_session.flush()

    i = 0
    for predicted, actual, count in groups:
        for _ in range(count):
            ts = now - timedelta(days=2 + i, hours=1)
            i += 1
            pred = Prediction(
                instrument_id=instrument.id,
                model_version_id=version.id,
                horizon="1d",
                predicted_direction=predicted,
                up_probability=Decimal("0.34"),
                neutral_probability=Decimal("0.34"),
                down_probability=Decimal("0.32"),
                expected_return=Decimal("0"),
                range_lower=Decimal("-0.02"),
                range_upper=Decimal("0.02"),
                confidence=51,
                prediction_timestamp=ts,
                data_timestamp=ts,
                features_snapshot={},
            )
            db_session.add(pred)
            await db_session.flush()
            db_session.add(
                PredictionOutcome(
                    prediction_id=pred.id,
                    actual_return=Decimal("0.1") if actual == "neutral" else Decimal("1.0"),
                    actual_direction=actual,
                    # Legacy flag says "correct" for neutral-vs-neutral.
                    is_correct=(predicted == actual),
                    evaluation_price=Decimal("100"),
                    evaluation_timestamp=ts + timedelta(days=1),
                    evaluated_at=now - timedelta(hours=1, minutes=i),
                    source="test",
                )
            )
    await db_session.commit()


@pytest.mark.asyncio
async def test_neutral_predictions_do_not_inflate_analytics(db_session):
    from services.mlops.analytics import compute_performance_analytics

    # 29 neutral-vs-neutral "correct" rows + 11 directional correct rows.
    await _seed(db_session, [("neutral", "neutral", 29), ("up", "up", 11)])

    result = await compute_performance_analytics(db_session, days=90)
    assert result["summary"]["n"] == 40
    assert result["summary"]["directional_n"] == 11
    assert result["summary"]["neutral_n"] == 29
    assert result["summary"]["accuracy"] == pytest.approx(1.0)
    assert result["summary"]["all_class_accuracy"] == pytest.approx(1.0)
    # The old buggy formula would have returned exact-class accuracy (1.0)
    # over all 40 rows; the canonical formula only counts 11 directional
    # calls. Crucially a neutral-only model returns None, tested elsewhere.
    assert result["summary"]["directional_correct"] == 11
    assert result["summary"]["neutral_correct"] == 29


@pytest.mark.asyncio
async def test_history_route_reports_null_accuracy_and_dedupes_bars(db_session):
    """API contract: small directional samples are not a hit rate, and
    duplicate inference runs for the same bar are counted once."""
    from sqlalchemy import select

    from apps.api.models.prediction import Prediction
    from apps.api.routes.predictions import get_prediction_history

    await _seed(db_session, [("neutral", "neutral", 29), ("up", "up", 11)])

    # Simulate a legacy duplicate inference run for the same bar/model.
    original = (
        await db_session.execute(select(Prediction).limit(1))
    ).scalar_one()
    duplicate = Prediction(
        instrument_id=original.instrument_id,
        model_version_id=original.model_version_id,
        horizon=original.horizon,
        predicted_direction=original.predicted_direction,
        up_probability=original.up_probability,
        neutral_probability=original.neutral_probability,
        down_probability=original.down_probability,
        expected_return=original.expected_return,
        range_lower=original.range_lower,
        range_upper=original.range_upper,
        confidence=original.confidence,
        prediction_timestamp=original.prediction_timestamp,
        data_timestamp=original.data_timestamp,
        features_snapshot={},
    )
    db_session.add(duplicate)
    await db_session.commit()

    response = await get_prediction_history(
        symbol="AAPL",
        exchange="NASDAQ",
        horizon="1d",
        limit=100,
        session=db_session,
    )

    assert response.summary.total_predictions == 40
    assert response.summary.directional_count == 11
    assert response.summary.neutral_predictions == 29
    # Below MIN_SAMPLE, so no headline accuracy is emitted.
    assert response.summary.accuracy is None
    assert response.summary.accuracy_reliable is False
    assert response.summary.minimum_sample == 30
    assert response.summary.correct_predictions == 11
    assert response.summary.incorrect_predictions == 0

    neutral_items = [i for i in response.items if i.prediction == "neutral"]
    assert neutral_items and all(i.result == "neutral" for i in neutral_items)
    assert all(i.counted_in_accuracy is False for i in neutral_items)
    directional_items = [i for i in response.items if i.prediction == "up"]
    assert directional_items and all(i.counted_in_accuracy for i in directional_items)


@pytest.mark.asyncio
async def test_history_route_dedupes_legacy_wallclock_duplicates(db_session):
    """Legacy rows carry wall-clock timestamps (pre-PIT fix). N runs for the
    same underlying bar must count ONCE, keyed on the bar's UTC date."""
    from datetime import datetime

    from sqlalchemy import select

    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import Model, ModelVersion, Prediction, PredictionOutcome
    from apps.api.models.price import PriceBar
    from apps.api.routes.predictions import get_prediction_history

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

    # Bar day D (double-stamped 00:00 and 04:00 UTC like multi-provider data),
    # and the next trading bar D+1 that resolves the outcome.
    day_d = (now - timedelta(days=5)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_next = day_d + timedelta(days=1)
    for ts in (day_d, day_d + timedelta(hours=4), day_next, day_next + timedelta(hours=4)):
        db_session.add(
            PriceBar(
                instrument_id=instrument.id, timeframe="1d", timestamp=ts,
                open=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
                close=Decimal("100"), volume=1000,
            )
        )
    await db_session.flush()

    # Three legacy wall-clock runs on the same bar day (distinct timestamps),
    # all using the D close as base price.
    base_price = 100.0
    for run_hour in (6, 9, 11):
        ts = day_next.replace(hour=run_hour, minute=13, second=17)
        pred = Prediction(
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
            prediction_timestamp=ts,
            data_timestamp=ts,  # legacy: wall clock, not bar timestamp
            features_snapshot={"price": base_price},
        )
        db_session.add(pred)
        await db_session.flush()
        db_session.add(
            PredictionOutcome(
                prediction_id=pred.id,
                actual_return=Decimal("1.0"),
                actual_direction="up",
                is_correct=True,
                evaluation_price=Decimal("101"),
                evaluation_timestamp=day_next + timedelta(hours=4),
                evaluated_at=now - timedelta(hours=1, minutes=run_hour),
                source="test",
            )
        )
    await db_session.commit()

    response = await get_prediction_history(
        symbol="MSFT", exchange="NASDAQ", horizon="1d", limit=100, session=db_session,
    )
    # Three wall-clock duplicates collapse to ONE forecast for the bar day.
    assert response.summary.total_predictions == 1
    assert response.summary.directional_count == 1
    assert response.summary.correct_predictions == 1
    # Small-sample policy: n=1 is far below MIN_SAMPLE so no headline
    # accuracy is emitted — but the count proves dedupe worked.
    assert response.summary.accuracy is None
    assert response.summary.accuracy_reliable is False
    assert response.summary.correct_predictions == 1
