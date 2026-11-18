"""Generate and persist immutable per-prediction explanations.

The feature vector is read from ``Prediction.features_snapshot`` — the exact
values used at inference time — never recomputed from later bars. The model
is the hash-verified champion artifact that produced the prediction. If the
prediction belongs to a different model version, explanation fails closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.prediction import Prediction, PredictionExplanation
from services.ml import recipe
from services.ml.champion import (
    V10_CANDIDATE_PATHS,
    resolve_champion,
    resolve_champion_artifact,
    sha_accepted,
    sha_of,
)
from services.ml.explainability import (
    EXPLAINER_VERSION,
    ExplanationError,
    explain_feature_vector,
)

_ARTIFACT_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}


class ExplanationUnavailableError(ExplanationError):
    """Explanation cannot be generated; callers return a disclosed 409."""


def _candidate_paths() -> list[Path]:
    paths = list(V10_CANDIDATE_PATHS)
    paths.append(Path(__file__).resolve().parents[3] / "model_artifacts" / "real" / "ensemble" / "v1.0" / "model.pkl")
    return paths


def _load_verified_artifact(expected_sha: str, prefix_ok: bool) -> tuple[dict[str, Any], str]:
    for path in _candidate_paths():
        if not path.exists() or not path.is_file():
            continue
        actual = sha_of(path)
        if not sha_accepted(actual, expected_sha, prefix_ok):
            continue
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = _ARTIFACT_CACHE.get(key)
        if cached is None:
            cached = joblib.load(path)
            _ARTIFACT_CACHE.clear()
            _ARTIFACT_CACHE[key] = cached
        return cached, actual
    raise ExplanationUnavailableError(
        "Champion artifact is missing or failed hash verification; refusing to explain"
    )


async def _load_production_artifact(session: AsyncSession) -> tuple[dict[str, Any], str, str | None]:
    resolved = await resolve_champion_artifact(session)
    if resolved["kind"] == "experiment":
        path = Path(resolved["artifact_path"])
        if not path.exists() or not path.is_file():
            raise ExplanationUnavailableError("Champion experiment artifact is missing")
        actual = sha_of(path)
        if not sha_accepted(actual, resolved["artifact_sha"], False):
            raise ExplanationUnavailableError("Champion experiment artifact failed hash verification")
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = _ARTIFACT_CACHE.get(key)
        if cached is None:
            cached = joblib.load(path)
            _ARTIFACT_CACHE.clear()
            _ARTIFACT_CACHE[key] = cached
        return cached, actual, str(resolved["model_version_id"])
    champ = await resolve_champion(session)
    payload, actual = _load_verified_artifact(champ["artifact_sha"], champ["sha_is_prefix"])
    version_id = str(champ["model_version_id"]) if champ["model_version_id"] else None
    return payload, actual, version_id


async def _model_version_label(session: AsyncSession, prediction: Prediction) -> str:
    from apps.api.models.prediction import ModelVersion

    mv = await session.get(ModelVersion, prediction.model_version_id)
    return getattr(mv, "version", None) or "real-v1.0"


def _feature_values(prediction: Prediction, feature_names: list[str]) -> list[float]:
    snapshot = prediction.features_snapshot or {}
    missing = [name for name in feature_names if name not in snapshot]
    if missing:
        raise ExplanationUnavailableError(
            f"Prediction snapshot is missing {len(missing)} required features",
            missing=missing,
        )
    return [snapshot[name] for name in feature_names]


async def get_explanation(session: AsyncSession, prediction: Prediction) -> dict[str, Any]:
    existing = (
        await session.execute(
            select(PredictionExplanation).where(
                PredictionExplanation.prediction_id == prediction.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.payload

    await session.refresh(prediction)
    artifact, artifact_sha, champion_version_id = await _load_production_artifact(session)
    prediction_version_id = str(prediction.model_version_id)
    if champion_version_id is not None and prediction_version_id != champion_version_id:
        raise ExplanationUnavailableError(
            "Prediction was produced by a non-current model version; its artifact is unavailable. "
            "Explanations are only served for the verified production champion."
        )

    model = artifact.get("model")
    scaler = artifact.get("scaler")
    calibrator = artifact.get("calibrator")
    feature_names = artifact.get("features") or artifact.get("feature_names")
    if model is None or scaler is None or not feature_names:
        raise ExplanationUnavailableError("Champion artifact is missing model, scaler, or features")
    if hasattr(scaler, "n_features_in_") and scaler.n_features_in_ != len(feature_names):
        raise ExplanationUnavailableError("Champion scaler dimension does not match feature schema")

    values = _feature_values(prediction, list(feature_names))
    direction = str(
        prediction.predicted_direction.value
        if hasattr(prediction.predicted_direction, "value")
        else prediction.predicted_direction
    )
    served = {
        "up": float(prediction.up_probability),
        "neutral": float(prediction.neutral_probability),
        "down": float(prediction.down_probability),
    }
    max_prob = max(served.values())
    no_edge = max_prob < recipe.NO_EDGE_THRESHOLD

    try:
        payload = explain_feature_vector(
            estimator=model,
            scaler=scaler,
            calibrator=calibrator,
            feature_names=list(feature_names),
            feature_values=values,
            predicted_direction=direction,
            served_probabilities=served,
            no_clear_edge=no_edge,
        )
    except ExplanationError as exc:
        raise ExplanationUnavailableError(str(exc), missing=getattr(exc, "missing", [])) from exc

    from apps.api.models.market import Exchange, Instrument

    instrument = await session.get(Instrument, prediction.instrument_id)
    exchange = await session.get(Exchange, instrument.exchange_id) if instrument else None
    payload.update(
        {
            "prediction_id": str(prediction.id),
            "symbol": getattr(instrument, "symbol", None),
            "exchange": getattr(exchange, "code", None),
            "horizon": prediction.horizon,
            "model_horizon": recipe.MODEL_NATIVE_HORIZON,
            "predicted_direction": direction,
            "model_version": await _model_version_label(session, prediction),
            "artifact_sha": artifact_sha,
            "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
            "data_timestamp": prediction.data_timestamp.isoformat(),
            "generated_at": None,
            "explainer_version": EXPLAINER_VERSION,
        }
    )

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    payload["generated_at"] = now.isoformat()
    row = PredictionExplanation(
        prediction_id=prediction.id,
        explainer_version=EXPLAINER_VERSION,
        method=payload["explainer"]["method"],
        model_version=payload["model_version"],
        artifact_sha=artifact_sha,
        feature_vector_hash=payload["feature_vector_hash"],
        predicted_direction=direction,
        payload=payload,
    )
    session.add(row)
    try:
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        existing = (
            await session.execute(
                select(PredictionExplanation).where(
                    PredictionExplanation.prediction_id == prediction.id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.payload
        raise
    return payload


async def get_explanation_by_id(session: AsyncSession, prediction_id) -> dict[str, Any]:
    prediction = await session.get(Prediction, prediction_id)
    if prediction is None:
        raise ExplanationUnavailableError("Prediction not found")
    return await get_explanation(session, prediction)
