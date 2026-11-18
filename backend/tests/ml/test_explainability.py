"""Explainability integrity tests (Phase 1).

Proofs:
1. TreeSHAP contributions reconcile with the model output.
2. Explanations are bound to a deterministic feature-vector hash.
3. Different feature vectors produce different drivers (no fixed template).
4. Missing features are disclosed, never silently zero-filled.
5. Persisted explanations are immutable (second read returns the same row).
6. The API route returns the explanation for the requested prediction id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from services.ml.explainability import (
    ExplanationError,
    explain_feature_vector,
    feature_vector_hash,
)

ARTIFACT = Path("model_artifacts/real/ensemble/v1.0/model.pkl")
if not ARTIFACT.exists():
    ARTIFACT = Path("backend/model_artifacts/real/ensemble/v1.0/model.pkl")


@pytest.fixture(scope="module")
def artifact():
    if not ARTIFACT.exists():
        pytest.skip("production artifact not present")
    data = joblib.load(ARTIFACT)
    return data


def _feature_vector(artifact, adjustments: dict[str, float] | None = None) -> list[float]:
    names = artifact["features"]
    scaler = artifact["scaler"]
    values = [float(v) for v in scaler.mean_]
    for name, value in (adjustments or {}).items():
        values[names.index(name)] = value
    return values


def _served(artifact, values: list[float]) -> dict[str, float]:
    names = artifact["features"]
    x = artifact["scaler"].transform(pd.DataFrame([values], columns=names))
    probs = artifact["calibrator"].predict_proba(x)[0]
    return {"down": float(probs[0]), "neutral": float(probs[1]), "up": float(probs[2])}


def _direction(served: dict[str, float]) -> str:
    return max(served, key=served.get)


def test_treeshap_contributions_reconcile_with_model_output(artifact):
    values = _feature_vector(
        artifact, {"rsi_14": 71.0, "roc_5d": 0.04, "realized_vol_20d": 18.0}
    )
    served = _served(artifact, values)
    direction = _direction(served)
    result = explain_feature_vector(
        artifact["model"],
        artifact["scaler"],
        artifact["calibrator"],
        artifact["features"],
        values,
        direction,
        served,
    )
    assert result["explainer"]["method"] == "tree_shap"
    assert result["reconciliation"]["matches_model_output"] is True
    assert result["reconciliation"]["max_abs_error"] <= result["reconciliation"]["tolerance"]
    assert result["reconciliation"]["direction_matches_saved"] is True
    assert result["feature_vector_hash"] == feature_vector_hash(artifact["features"], values)


def test_explanations_are_prediction_specific(artifact):
    base = _feature_vector(artifact)
    bullish = _feature_vector(
        artifact, {"roc_5d": 0.09, "roc_20d": 0.18, "rel_volume_20d": 3.2, "rsi_14": 74.0}
    )
    bearish = _feature_vector(
        artifact, {"roc_5d": -0.09, "roc_20d": -0.18, "rel_volume_20d": 3.2, "rsi_14": 22.0}
    )
    out = []
    for vector in (bullish, bearish):
        served = _served(artifact, vector)
        out.append(
            explain_feature_vector(
                artifact["model"],
                artifact["scaler"],
                artifact["calibrator"],
                artifact["features"],
                vector,
                _direction(served),
                served,
            )
        )
    assert out[0]["feature_vector_hash"] != out[1]["feature_vector_hash"]
    assert out[0]["narrative"]["summary"] != out[1]["narrative"]["summary"]
    assert out[0]["top_positive"][0]["feature"] != out[1]["top_positive"][0]["feature"] or (
        out[0]["top_positive"][0]["contribution"] != out[1]["top_positive"][0]["contribution"]
    )
    # The unchanged baseline vector must be reproducible.
    base_result = explain_feature_vector(
        artifact["model"],
        artifact["scaler"],
        artifact["calibrator"],
        artifact["features"],
        base,
        _direction(_served(artifact, base)),
        _served(artifact, base),
    )
    assert base_result["feature_vector_hash"] == feature_vector_hash(artifact["features"], base)


def test_missing_features_are_disclosed(artifact):
    values = _feature_vector(artifact)
    values[3] = float("nan")
    with pytest.raises(ExplanationError) as exc:
        explain_feature_vector(
            artifact["model"],
            artifact["scaler"],
            artifact["calibrator"],
            artifact["features"],
            values,
            "neutral",
            {"down": 0.3, "neutral": 0.4, "up": 0.3},
        )
    assert artifact["features"][3] in exc.value.missing


async def _seed_prediction(session, artifact):
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import Model, ModelVersion, Prediction

    market = Market(
        code=f"T{uuid.uuid4().hex[:4]}",
        name="Test Market",
        country_code="USA",
        currency="USD",
        timezone="America/New_York",
        market_open=datetime(2000, 1, 1, 14, 30).time(),
        market_close=datetime(2000, 1, 1, 21, 0).time(),
    )
    session.add(market)
    await session.flush()
    exchange = Exchange(
        code=f"EX{uuid.uuid4().hex[:4]}",
        name="Test Exchange",
        market_id=market.id,
        timezone="America/New_York",
        currency="USD",
        market_open=datetime(2000, 1, 1, 14, 30).time(),
        market_close=datetime(2000, 1, 1, 21, 0).time(),
    )
    session.add(exchange)
    await session.flush()
    instrument = Instrument(
        symbol=f"TST{uuid.uuid4().hex[:4].upper()}",
        name="Test Instrument",
        exchange_id=exchange.id,
        currency="USD",
        type="equity",
    )
    session.add(instrument)
    model = Model(name=f"test-model-{uuid.uuid4().hex[:8]}", model_type="ensemble")
    session.add(model)
    await session.flush()
    version = ModelVersion(model_id=model.id, version="real-v1.0", metrics={}, hyperparameters={})
    session.add(version)
    await session.flush()

    values = _feature_vector(
        artifact, {"rsi_14": 68.0, "roc_5d": 0.05, "realized_vol_20d": 24.0}
    )
    served = _served(artifact, values)
    direction = _direction(served)
    snapshot = {name: value for name, value in zip(artifact["features"], values, strict=True)}
    snapshot["price"] = 100.0
    snapshot["change_percent"] = 0.5
    now = datetime.now(UTC)
    prediction = Prediction(
        instrument_id=instrument.id,
        model_version_id=version.id,
        horizon="1d",
        predicted_direction=direction,
        up_probability=Decimal(str(round(served["up"], 4))),
        neutral_probability=Decimal(str(round(served["neutral"], 4))),
        down_probability=Decimal(str(round(served["down"], 4))),
        expected_return=Decimal(str(round((served["up"] - served["down"]) * 2, 4))),
        range_lower=Decimal("-1"),
        range_upper=Decimal("1"),
        confidence=55,
        prediction_timestamp=now,
        data_timestamp=now,
        features_snapshot=snapshot,
    )
    session.add(prediction)
    await session.commit()
    return prediction


@pytest.mark.asyncio
async def test_explanation_persists_immutably(db_session, artifact):
    from sqlalchemy import func, select

    from apps.api.models.prediction import PredictionExplanation
    from services.prediction.explanation_service import get_explanation

    prediction = await _seed_prediction(db_session, artifact)
    first = await get_explanation(db_session, prediction)
    second = await get_explanation(db_session, prediction)
    assert first["prediction_id"] == str(prediction.id)
    assert first["generated_at"] == second["generated_at"]
    count = (
        await db_session.execute(select(func.count(PredictionExplanation.id)))
    ).scalar_one()
    assert count == 1
    assert first["feature_vector_hash"] == second["feature_vector_hash"]
    assert first["reconciliation"]["matches_model_output"] is True


@pytest.mark.asyncio
async def test_explanation_route_matches_prediction(db_session, artifact):
    from apps.api.routes.predictions import get_prediction_explanation

    prediction = await _seed_prediction(db_session, artifact)
    response = await get_prediction_explanation(prediction.id, db_session)
    assert response.prediction_id == prediction.id
    assert response.predicted_direction == str(prediction.predicted_direction)
    assert response.model_horizon == "1d"
    assert response.contributions
    assert response.reconciliation["direction_matches_saved"] is True
