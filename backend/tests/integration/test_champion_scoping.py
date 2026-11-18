"""Champion scoping: shadow/retired-challenger predictions must never
surface as production predictions (latest, top, screener, alert eval).

Regression for Oct 2026 finding: integration-test challenger versions left
shadow rows that unfiltered listings would have presented as production.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest


async def _shadow_row(session):
    """Insert one shadow-version prediction for AAPL (visible if unscoped)."""
    import uuid as _uuid

    from sqlalchemy import select

    from apps.api.models.market import Instrument
    from apps.api.models.prediction import Model, ModelVersion, Prediction

    inst = (
        await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
    ).scalars().first()
    model = Model(name=f"test-shadow-scope-{_uuid.uuid4().hex[:8]}", description="scope probe", model_type="ensemble", is_active=True)
    session.add(model)
    await session.flush()
    version = ModelVersion(
        model_id=model.id, version="shadow-1", description="scope probe",
        is_active=True, training_date=datetime.now(UTC),
        metrics={}, hyperparameters={},
    )
    session.add(version)
    await session.flush()
    now = datetime.now(UTC)
    row = Prediction(
        instrument_id=inst.id, model_version_id=version.id, horizon="1d",
        predicted_direction="up",
        up_probability=Decimal("0.99"), neutral_probability=Decimal("0.005"),
        down_probability=Decimal("0.005"), expected_return=Decimal("9.9"),
        range_lower=Decimal("-1"), range_upper=Decimal("2"), confidence=99,
        prediction_timestamp=now, data_timestamp=now,
        features_snapshot={"price": 1.0, "change_percent": 0.0},
    )
    session.add(row)
    await session.commit()
    return row.id, version.id


@pytest.mark.asyncio
async def test_shadow_predictions_excluded_from_production_reads():
    from sqlalchemy import select

    from apps.api.database import async_session_factory
    from apps.api.models.prediction import Prediction
    from apps.api.repositories.prediction import PredictionRepository

    async with async_session_factory() as session:
        row_id, _ = await _shadow_row(session)
        repo = PredictionRepository(session)
        # Latest-for-instrument (stock page, factors, alerts, scheduler checks).
        from apps.api.models.market import Instrument

        inst = (
            await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
        ).scalars().first()
        latest = await repo.get_latest_for_instrument(inst.id, "1d")
        assert latest is None or latest.id != row_id
        # Top listings.
        top = await repo.get_top_predictions(horizon="1d", limit=200)
        assert row_id not in {p.id for p in top}
        # Explicit version reads still work (audit/shadow comparison paths).
        by_version = await repo.get_latest_for_instrument(
            inst.id, "1d", model_version_id=(await session.get(Prediction, row_id)).model_version_id,
            champion_only=False,
        )
        assert by_version is not None and by_version.id == row_id
        # Cleanup probe rows.
        await session.delete(await session.get(Prediction, row_id))
        await session.commit()
