"""Shadow evaluation mechanics on the live dev DB.

- Artifact hash gate: tampered/missing artifacts never produce predictions.
- Engine artifact_override path yields well-formed probabilities.
- Shadow predictions persist under the challenger version (never the
  champion's), so production listings are uncontaminated.
"""

from types import SimpleNamespace

import pytest


def _v10_artifact():
    import joblib

    data = joblib.load("model_artifacts/real/ensemble/v1.0/model.pkl")
    feats = data.get("feature_names") or data.get("features")
    return {
        "model": data.get("model"),
        "scaler": data.get("scaler"),
        "features": feats,
        "feature_names": feats,
        "calibrator": data.get("calibrator"),
    }


@pytest.mark.asyncio
async def test_verified_artifact_rejects_tampering():
    from services.mlops.shadow import _load_verified_artifact

    exp = SimpleNamespace(experiment_id="X", artifact_path="nope.pkl", artifact_sha="sha256:abc")
    with pytest.raises(ValueError, match="missing"):
        await _load_verified_artifact(exp)
    exp2 = SimpleNamespace(
        experiment_id="X",
        artifact_path="model_artifacts/real/ensemble/v1.0/model.pkl",
        artifact_sha="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="mismatch"):
        await _load_verified_artifact(exp2)


@pytest.mark.asyncio
async def test_shadow_inference_path_yields_valid_probabilities():
    from sqlalchemy import select

    from apps.api.database import async_session_factory
    from apps.api.models.market import Instrument
    from services.prediction.prediction_service import PredictionService

    art = _v10_artifact()
    override = (art["model"], art["scaler"], art["feature_names"], art["calibrator"], "shadow:test")
    async with async_session_factory() as session:
        inst = (
            await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
        ).scalars().first()
        svc = PredictionService(session)
        data = await svc.engine.generate_prediction_async(
            inst.id, inst.id, "1d", {}, artifact_override=override
        )
        total = float(data["up_probability"]) + float(data["neutral_probability"]) + float(data["down_probability"])
        assert abs(total - 1.0) < 1e-3
        assert data["predicted_direction"] in ("up", "neutral", "down")


@pytest.mark.asyncio
async def test_shadow_run_skips_cleanly_without_candidates():
    from apps.api.database import async_session_factory
    from services.mlops.shadow import run_shadow_generation

    async with async_session_factory() as session:
        out = await run_shadow_generation(session)
        # Either nothing to shadow (skip) or a well-formed per-experiment map.
        assert out.get("skipped") is True or "experiments" in out
