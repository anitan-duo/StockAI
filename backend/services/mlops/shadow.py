"""Shadow evaluation: challenger predicts alongside the champion.

- Champion serving is untouched (separate ModelVersion rows, separate
  predictions keyed by the challenger version id).
- Challenger artifacts are hash-verified against the experiment record
  before a single byte is trusted.
- No live trading, no user visibility: shadow rows are queryable only by
  version id (MLOps API/UI), never mixed into production listings.
"""

from __future__ import annotations

from datetime import UTC, datetime

import joblib
from sqlalchemy import select


async def _load_verified_artifact(experiment) -> dict:
    from services.ml.champion import sha_accepted, sha_of
    from pathlib import Path

    if not experiment.artifact_path or not experiment.artifact_sha:
        raise ValueError(f"experiment {experiment.experiment_id} has no artifact")
    path = Path(experiment.artifact_path)
    if not path.exists():
        raise ValueError(f"artifact missing: {path}")
    actual = sha_of(path)
    if not sha_accepted(actual, experiment.artifact_sha, False):
        raise ValueError(
            f"artifact hash mismatch for {experiment.experiment_id}: "
            f"recorded {experiment.artifact_sha[:19]}, file {actual[:19]}"
        )
    data = joblib.load(path)
    for key in ("model", "scaler", "features", "ensemble"):
        if data.get(key) is None and key != "ensemble":
            raise ValueError(f"artifact incomplete: missing {key}")
    return data


async def _challenger_version(session, experiment):
    """Get-or-create the shadow Model/ModelVersion rows for an experiment."""
    from apps.api.models.prediction import Model, ModelVersion

    name = f"challenger-{experiment.experiment_id}"
    model = (
        await session.execute(select(Model).where(Model.name == name))
    ).scalar_one_or_none()
    if model is None:
        model = Model(
            name=name,
            description=f"Shadow challenger for {experiment.experiment_id}. Never production without approval.",
            model_type="ensemble",
            is_active=True,
        )
        session.add(model)
        await session.flush()
    version = (
        await session.execute(
            select(ModelVersion)
            .where(ModelVersion.model_id == model.id, ModelVersion.version == "shadow-1")
        )
    ).scalar_one_or_none()
    if version is None:
        version = ModelVersion(
            model_id=model.id,
            version="shadow-1",
            description=f"Shadow weights for {experiment.experiment_id}",
            is_active=True,
            training_date=datetime.now(UTC),
            metrics=dict(experiment.metrics or {}),
            hyperparameters=dict((experiment.hyperparameters or {})),
        )
        session.add(version)
        await session.flush()
    return model, version


async def run_shadow_generation(session, limit_instruments: int = 100) -> dict:
    """Generate one shadow prediction round for candidate/shadow experiments."""
    from sqlalchemy.orm import selectinload

    from apps.api.models.market import Exchange, Instrument
    from apps.api.models.mlops import Experiment
    from services.prediction.prediction_service import PredictionService

    exps = (
        await session.execute(
            select(Experiment).where(Experiment.status.in_(["candidate", "shadow"]))
        )
    ).scalars().all()
    if not exps:
        return {"skipped": True, "reason": "no candidate/shadow experiments"}
    insts = (
        await session.execute(
            select(Instrument)
            .options(selectinload(Instrument.exchange))
            .where(Instrument.is_active.is_(True))
            .limit(limit_instruments)
        )
    ).scalars().all()
    specs = [(i.id, i.symbol) for i in insts]
    out: dict = {"experiments": {}}
    for exp in exps:
        ok, skipped, failed = [], [], []
        try:
            artifact = await _load_verified_artifact(exp)
            feats = artifact.get("feature_names") or artifact.get("features")
            override = (
                artifact.get("model"),
                artifact.get("scaler"),
                feats,
                artifact.get("calibrator"),
                f"shadow:{exp.experiment_id}",
            )
            _, version = await _challenger_version(session, exp)
            svc = PredictionService(session)
            for inst_id, symbol in specs:
                try:
                    pred_data = await svc.engine.generate_prediction_async(
                        inst_id, version.id, "1d", {}, artifact_override=override,
                    )
                    await svc.persist_shadow_prediction(inst_id, version.id, pred_data)
                    await session.commit()
                    ok.append(symbol)
                except Exception as e:  # noqa: BLE001 - per-item isolation
                    failed.append({"symbol": symbol, "error": str(e)[:200]})
                    try:
                        await session.rollback()
                    except Exception:
                        pass
            if exp.status == "candidate":
                exp.status = "shadow"
                await session.commit()
        except Exception as e:  # noqa: BLE001 - experiment-level isolation
            failed.append({"experiment": exp.experiment_id, "error": str(e)[:200]})
        out["experiments"][exp.experiment_id] = {
            "ok": len(ok), "skipped": len(skipped), "failed": failed[:5],
            "status": exp.status,
        }
    return out
