from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.database import get_session
from apps.api.routes.auth import get_current_user
from services.ml.registry import ModelRegistry
from services.ml.training import ModelTrainer, create_training_pipeline
from services.ml.features import create_feature_matrix
from services.ml.registry import ModelRegistry
from services.prediction.indicator_service import IndicatorService
from apps.api.repositories.market import InstrumentRepository
from apps.api.repositories.prediction import PredictionRepository

router = APIRouter(prefix="/training", tags=["training"])


def _require_superuser(user) -> None:
    """Gate expensive/promoting training operations to admins."""
    is_admin = bool(getattr(user, "is_superuser", False))
    if isinstance(user, dict):
        is_admin = bool(user.get("is_superuser", False))
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


class TrainingRequest(BaseModel):
    market_codes: Optional[list[str]] = None
    lookback_days: int = 730
    horizon: str = "1d"
    target_definition: Optional[dict] = None


class TrainingResponse(BaseModel):
    status: str
    message: str
    training_id: Optional[str] = None
    metrics: Optional[dict] = None


@router.post("/run", response_model=TrainingResponse)
async def run_training(
    request: TrainingRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TrainingResponse:
    """Trigger model training pipeline (admin only)."""
    _require_superuser(user)
    try:
        # Get active instruments (eager-load exchange.market: lazy access
        # here raises MissingGreenlet under async SQLAlchemy).
        from sqlalchemy import select as _select
        from sqlalchemy.orm import selectinload as _selectinload

        from apps.api.models.market import Exchange as _Exchange
        from apps.api.models.market import Instrument as _Instrument

        stmt = (
            _select(_Instrument)
            .options(_selectinload(_Instrument.exchange).selectinload(_Exchange.market))
            .where(_Instrument.is_active.is_(True))
            .order_by(_Instrument.symbol)
            .limit(100)
        )
        instruments = list((await session.execute(stmt)).scalars().all())

        if request.market_codes:
            wanted = {c.upper() for c in request.market_codes}
            instruments = [
                inst for inst in instruments
                if inst.exchange and inst.exchange.market and inst.exchange.market.code.upper() in wanted
            ]

        if not instruments:
            raise HTTPException(status_code=400, detail="No instruments available for training")

        # Prepare data
        instruments_data = {}
        for inst in instruments[:50]:  # Limit to 50 instruments
            from apps.api.repositories.market import PriceBarRepository
            price_bar_repo = PriceBarRepository(session)
            bars = await price_bar_repo.get_range(
                inst.id, "1d",
                datetime.now(UTC) - timedelta(days=request.lookback_days),
                datetime.now(UTC),
            )
            if len(bars) > 100:
                import pandas as pd
                df = pd.DataFrame([{
                    "date": b.timestamp,
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": b.volume,
                } for b in bars])
                df.set_index("date", inplace=True)
                instruments_data[inst.symbol] = df

        if not instruments_data:
            raise HTTPException(status_code=400, detail="Insufficient historical data for training")

        # Run training pipeline
        trainer, report = create_training_pipeline(
            instruments_data=instruments_data,
            reference_date=datetime.now(UTC),
        )

        return TrainingResponse(
            status="success",
            message="Model training completed successfully",
            metrics=report.get("evaluation_results", {}).get("aggregate", {}),
        )

    except HTTPException:
        raise
    except Exception:
        import logging

        logging.getLogger("stockai.api").exception("training failed")
        raise HTTPException(status_code=500, detail="Training failed")


@router.get("/models")
async def list_models(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """List available models in registry."""
    registry = ModelRegistry(session)
    models = {}
    for name in registry.models:
        models[name] = registry.list_versions(name)
    return models


@router.post("/models/{model_name}/activate/{version}")
async def activate_model_version(
    model_name: str,
    version: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Activate a model version (admin only)."""
    _require_superuser(user)
    registry = ModelRegistry(session)
    try:
        registry.set_active(model_name, version)
        return {"status": "success", "message": f"Activated {model_name} version {version}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/models/{model_name}/versions")
async def list_model_versions(
    model_name: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """List all versions of a model."""
    registry = ModelRegistry(session)
    versions = registry.list_versions(model_name)
    return versions


@router.post("/evaluate")
async def evaluate_model(
    model_name: str,
    version: str = "latest",
    test_days: int = 30,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Evaluate a model on recent data (admin only)."""
    _require_superuser(user)
    # This would run evaluation on recent data
    return {"status": "not_implemented", "message": "Model evaluation endpoint not yet implemented"}


@router.get("/calibration")
async def get_calibration(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Get calibration metrics for the active model (real walk-forward out-of-sample)."""
    import json
    import pathlib
    from fastapi.responses import JSONResponse

    candidates = [
        pathlib.Path("backend/model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                # Validate required fields
                required = ["model_version", "brier_score", "ece", "sample_count", "classes", "calibration_curve"]
                if all(k in data for k in required):
                    return data
            except Exception:
                continue
    # Also try legacy metrics.json
    for p in [
        pathlib.Path("backend/model_artifacts/ensemble/v1.0/metrics.json"),
        pathlib.Path("model_artifacts/ensemble/v1.0/metrics.json"),
    ]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if "brier_score" in data:
                    return data
            except Exception:
                pass
    return JSONResponse(
        status_code=503,
        content={"detail": "Calibration data unavailable: no valid calibration evaluation found. Run training with walk-forward evaluation."},
    )


@router.get("/registry/status")
async def get_registry_status(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Get model registry status."""
    registry = ModelRegistry(session)
    return {
        "models": {name: {"versions": len(versions), "active": registry.active_versions.get(name)} 
                   for name, versions in registry.models.items()},
        "active_models": registry.active_versions,
    }