from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.repositories.market import InstrumentRepository
from apps.api.repositories.prediction import (
    PredictionRepository,
)
from packages.schemas.prediction import (
    FactorAnalysisResponse,
    PredictionHistoryItem,
    PredictionHistoryResponse,
    PredictionExplanationResponse,
    PredictionPerformanceSummary,
    PredictionResponse,
    RsiAnalysisResponse,
    TopPredictionResponse,
)
from services.ml.recipe import MODEL_NATIVE_HORIZON, NO_EDGE_THRESHOLD
from services.prediction.evaluation import MIN_SAMPLE, make_record, score_records
from services.prediction.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _require_supported_horizon(horizon: str) -> None:
    """v1.0 is a 1-day model. Refuse to serve its probabilities under a 1w/1m
    label — that would market a forecast the model does not make (§15)."""
    if horizon != MODEL_NATIVE_HORIZON:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "UNSUPPORTED_HORIZON",
                "reason": (
                    f"prediction horizon '{horizon}' is not supported: model v1.0 "
                    f"natively forecasts {MODEL_NATIVE_HORIZON} (next trading day). "
                    "Request horizon=1d."
                ),
                "model_horizon": MODEL_NATIVE_HORIZON,
            },
        )


@router.get("/stocks/{symbol}", response_model=PredictionResponse)
async def get_stock_prediction(
    symbol: str,
    exchange: str = Query(...),
    horizon: str = Query(default="1d", pattern="^(1d|1w|1m)$"),
    session: AsyncSession = Depends(get_session),
) -> PredictionResponse:
    """Get latest prediction for a stock."""
    _require_supported_horizon(horizon)
    instrument_repo = InstrumentRepository(session)
    # Get exchange
    from apps.api.repositories.market import ExchangeRepository
    exchange_repo = ExchangeRepository(session)
    ex = await exchange_repo.get_by_code(exchange)
    if not ex:
        raise HTTPException(status_code=404, detail="Exchange not found")

    instrument = await instrument_repo.get_by_symbol_exchange(symbol.upper(), ex.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    prediction_repo = PredictionRepository(session)
    prediction = await prediction_repo.get_latest_for_instrument(instrument.id, horizon)

    if not prediction:
        # Generate prediction if none exists - unified pipeline, will raise InsufficientDataError if not enough history
        try:
            prediction_service = PredictionService(session)
            prediction = await prediction_service.generate_prediction(instrument.id, horizon)
            await session.flush()
            await session.commit()
            # Need to reload with relationships for response
            prediction = await prediction_repo.get_latest_for_instrument(instrument.id, horizon)
        except Exception as e:
            # Check for insufficient data
            from services.prediction.prediction_service import InsufficientDataError

            if isinstance(e, InsufficientDataError):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "status": "UNAVAILABLE",
                        "reason": str(e),
                        "required_bars": getattr(e, "required", 252),
                        "available_bars": getattr(e, "available", 0),
                        "instrument": symbol,
                        "exchange": exchange,
                    },
                )
            raise

    # Avoid serializing ORM objects - detach before nulling to prevent DB update
    if prediction:
        session.expunge(prediction)
        prediction.instrument = None  # type: ignore
        prediction.model_version = None  # type: ignore
        # Also clear outcome relationship for serialization
        if hasattr(prediction, 'outcome'):
            prediction.outcome = None  # type: ignore
    response = PredictionResponse.model_validate(prediction)
    response.model_horizon = MODEL_NATIVE_HORIZON
    try:
        max_prob = max(
            float(prediction.up_probability),
            float(prediction.neutral_probability),
            float(prediction.down_probability),
        )
        response.no_clear_edge = max_prob < NO_EDGE_THRESHOLD
        ordered = sorted(
            [
                float(prediction.up_probability),
                float(prediction.neutral_probability),
                float(prediction.down_probability),
            ],
            reverse=True,
        )
        response.top_probability = round(ordered[0], 4)
        response.probability_margin = round(ordered[0] - ordered[1], 4)
    except Exception:
        response.no_clear_edge = False
    return response


@router.get("/stocks/{symbol}/history", response_model=PredictionHistoryResponse)
async def get_prediction_history(
    symbol: str,
    exchange: str = Query(...),
    horizon: str = Query(default="1d", pattern="^(1d|1w|1m)$"),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> PredictionHistoryResponse:
    """Get prediction history for a stock."""
    _require_supported_horizon(horizon)
    from apps.api.repositories.market import ExchangeRepository

    exchange_repo = ExchangeRepository(session)
    ex = await exchange_repo.get_by_code(exchange)
    if not ex:
        raise HTTPException(status_code=404, detail="Exchange not found")

    instrument_repo = InstrumentRepository(session)
    instrument = await instrument_repo.get_by_symbol_exchange(symbol.upper(), ex.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    prediction_repo = PredictionRepository(session)
    predictions = await prediction_repo.get_history(
        instrument.id, horizon, limit=limit
    )

    # Build history items + canonical records from ONE evaluation engine.
    items = []
    records = []
    completed_returns = []

    # One row per (instrument, horizon, bar day, model version). Historical
    # duplicate inference runs must not inflate any hit-rate denominator.
    # Legacy rows carry wall-clock timestamps, so the bar a forecast belongs
    # to is derived from price bars (latest bar <= prediction time).
    from services.prediction.bar_identity import bar_day, load_bar_day_index

    bar_index = await load_bar_day_index(session, [instrument.id])
    latest_by_bar: dict[tuple, object] = {}
    for pred in predictions:
        bar_key = (
            pred.instrument_id,
            pred.horizon,
            pred.model_version_id,
            bar_day(bar_index, pred.instrument_id, pred.prediction_timestamp),
        )
        existing = latest_by_bar.get(bar_key)
        if existing is None:
            latest_by_bar[bar_key] = pred
            continue
        existing_outcome = getattr(existing, "outcome", None)
        if existing_outcome is None and pred.outcome is not None:
            latest_by_bar[bar_key] = pred
        elif existing_outcome is not None and pred.outcome is not None:
            existing_at = getattr(existing_outcome, "evaluated_at", None)
            pred_at = getattr(pred.outcome, "evaluated_at", None)
            if pred_at is not None and (existing_at is None or pred_at > existing_at):
                latest_by_bar[bar_key] = pred

    for pred in latest_by_bar.values():
        pred_dir = str(
            pred.predicted_direction.value
            if hasattr(pred.predicted_direction, "value")
            else pred.predicted_direction
        )
        outcome = pred.outcome
        actual_dir = None
        actual_return = None
        if outcome is not None:
            actual_dir = str(
                outcome.actual_direction.value
                if hasattr(outcome.actual_direction, "value")
                else outcome.actual_direction
            )
            actual_return = outcome.actual_return
            completed_returns.append(outcome.actual_return)
        record = make_record(pred_dir, actual_dir, actual_return=actual_return)
        records.append(record)

        if not record.evaluated:
            result = None
        elif record.predicted == "neutral":
            result = "neutral"
        else:
            result = "correct" if record.directional_correct else "incorrect"

        mv = getattr(pred, "model_version", None)
        items.append(
            PredictionHistoryItem(
                date=pred.prediction_timestamp.strftime("%Y-%m-%d"),
                prediction=pred_dir,
                up_probability=pred.up_probability,
                expected_return=pred.expected_return,
                actual_return=actual_return,
                actual_direction=actual_dir,
                result=result,
                counted_in_accuracy=record.directional,
                model_version=getattr(mv, "version", None),
            )
        )

    scored = score_records(records, min_sample=MIN_SAMPLE)
    total_predictions = len(records)
    avg_return = (
        sum(completed_returns) / len(completed_returns)
        if completed_returns else Decimal("0")
    )
    accuracy_pct = (
        Decimal(str(scored["accuracy"] * 100)).quantize(Decimal("0.1"))
        if scored["accuracy"] is not None and scored["reliable"] else None
    )
    ci = scored["confidence_interval"]
    coverage = scored["coverage"]

    summary = PredictionPerformanceSummary(
        total_predictions=total_predictions,
        completed_count=scored["evaluated"],
        pending_count=scored["pending"],
        invalid_count=scored["invalid"],
        expired_count=scored["expired"],
        correct_predictions=scored["directional_correct"],
        incorrect_predictions=scored["directional_incorrect"],
        neutral_predictions=scored["neutral_n"],
        neutral_correct=scored["neutral_correct"],
        directional_count=scored["directional_n"],
        accuracy=accuracy_pct,
        accuracy_reliable=scored["reliable"],
        minimum_sample=scored["minimum_sample"],
        confidence_interval_lower=(
            Decimal(str(ci["lower"] * 100)).quantize(Decimal("0.1")) if ci else None
        ),
        confidence_interval_upper=(
            Decimal(str(ci["upper"] * 100)).quantize(Decimal("0.1")) if ci else None
        ),
        coverage=Decimal(str(coverage)).quantize(Decimal("0.0001")) if coverage is not None else None,
        scoring_policy=scored["scoring_policy"],
        average_return=avg_return.quantize(Decimal("0.01")),
    )

    return PredictionHistoryResponse(
        symbol=symbol.upper(),
        items=items,
        summary=summary,
    )


@router.get("/stocks/{symbol}/factors", response_model=FactorAnalysisResponse)
async def get_prediction_factors(
    symbol: str,
    exchange: str = Query(...),
    horizon: str = Query(default="1d", pattern="^(1d|1w|1m)$"),
    session: AsyncSession = Depends(get_session),
) -> FactorAnalysisResponse:
    """Get factor analysis for a prediction."""
    _require_supported_horizon(horizon)
    from apps.api.repositories.market import ExchangeRepository

    exchange_repo = ExchangeRepository(session)
    ex = await exchange_repo.get_by_code(exchange)
    if not ex:
        raise HTTPException(status_code=404, detail="Exchange not found")

    instrument_repo = InstrumentRepository(session)
    instrument = await instrument_repo.get_by_symbol_exchange(symbol.upper(), ex.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    prediction_repo = PredictionRepository(session)
    prediction = await prediction_repo.get_latest_for_instrument(instrument.id, horizon)

    if not prediction:
        raise HTTPException(status_code=404, detail="No prediction available")

    # Extract factors from features snapshot. Keys must match the unified
    # feature schema (feature_schema.json): rsi_14, macd/macd_histogram floats,
    # rel_volume_20d, realized_vol_20d. Previous code read nonexistent keys
    # (macd-as-dict, relative_volume_20, volatility_20) and always produced
    # empty/neutral output.
    features = prediction.features_snapshot
    positive = []
    neutral = []
    negative = []

    # RSI analysis
    rsi = features.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            positive.append("RSI oversold (< 30)")
        elif rsi > 70:
            negative.append("RSI overbought (> 70)")
        else:
            neutral.append(f"RSI neutral ({rsi:.0f})")

    # MACD analysis (macd/macd_histogram are floats in the unified schema)
    macd_hist = features.get("macd_histogram", features.get("macd", 0))
    try:
        macd_hist = float(macd_hist)
    except (TypeError, ValueError):
        macd_hist = 0.0
    if macd_hist > 0:
        positive.append("MACD histogram positive")
    elif macd_hist < 0:
        negative.append("MACD histogram negative")

    # Trend analysis
    sma_20 = features.get("sma_20")
    sma_50 = features.get("sma_50")
    if sma_20 and sma_50:
        if sma_20 > sma_50:
            positive.append("Price above 20-day SMA > 50-day SMA")
        else:
            negative.append("Price below 20-day SMA < 50-day SMA")

    # Volume analysis
    rel_vol = features.get("rel_volume_20d")
    if rel_vol and rel_vol > 1.5:
        positive.append("Above average volume")
    elif rel_vol and rel_vol < 0.5:
        negative.append("Below average volume")

    # Volatility (annualized percent in the unified schema)
    vol = features.get("realized_vol_20d")
    if vol and vol > 30:
        neutral.append("High volatility environment")

    return FactorAnalysisResponse(
        positive=positive,
        neutral=neutral,
        negative=negative,
    )


@router.get("/stocks/{symbol}/rsi", response_model=RsiAnalysisResponse)
async def get_stock_rsi(
    symbol: str,
    exchange: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> RsiAnalysisResponse:
    """RSI intelligence from persisted daily bars (point-in-time)."""
    from apps.api.repositories.market import ExchangeRepository, PriceBarRepository
    from services.prediction.rsi_service import analyze_rsi_bars

    exchange_repo = ExchangeRepository(session)
    ex = await exchange_repo.get_by_code(exchange)
    if not ex:
        raise HTTPException(status_code=404, detail="Exchange not found")
    instrument_repo = InstrumentRepository(session)
    instrument = await instrument_repo.get_by_symbol_exchange(symbol.upper(), ex.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    bars = await PriceBarRepository(session).get_latest(instrument.id, "1d", limit=400)
    bars = sorted(bars, key=lambda b: b.timestamp)
    if len(bars) < 40:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "UNAVAILABLE",
                "reason": f"Insufficient daily bars for RSI analysis: need 40, have {len(bars)}",
                "instrument": symbol,
                "exchange": exchange,
            },
        )
    import pandas as pd

    frame = pd.DataFrame(
        [{"close": float(b.close), "timestamp": b.timestamp} for b in bars]
    ).set_index("timestamp")
    direction = None
    prediction_timestamp = None
    prediction = await PredictionRepository(session).get_latest_for_instrument(instrument.id, "1d")
    if prediction is not None:
        raw_dir = prediction.predicted_direction
        direction = str(raw_dir.value if hasattr(raw_dir, "value") else raw_dir)
        prediction_timestamp = prediction.prediction_timestamp
    result = analyze_rsi_bars(frame, prediction_direction=direction)
    result.update(
        {
            "symbol": symbol.upper(),
            "exchange": exchange,
            "prediction_direction": direction,
            "prediction_timestamp": prediction_timestamp,
        }
    )
    return RsiAnalysisResponse.model_validate(result)


@router.get("/{prediction_id}/explanation", response_model=PredictionExplanationResponse)
async def get_prediction_explanation(
    prediction_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PredictionExplanationResponse:
    """Explain a saved prediction with the model and feature vector that produced it."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from apps.api.models.market import Instrument
    from apps.api.models.prediction import Prediction
    from services.prediction.explanation_service import (
        ExplanationUnavailableError,
        get_explanation,
    )

    prediction = (
        await session.execute(
            select(Prediction)
            .options(
                selectinload(Prediction.instrument).selectinload(Instrument.exchange),
                selectinload(Prediction.model_version),
            )
            .where(Prediction.id == prediction_id)
        )
    ).scalar_one_or_none()
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    try:
        payload = await get_explanation(session, prediction)
    except ExplanationUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "EXPLANATION_UNAVAILABLE",
                "reason": str(exc),
                "missing_features": getattr(exc, "missing", []),
            },
        ) from exc
    payload["horizon"] = str(prediction.horizon)
    payload["model_horizon"] = MODEL_NATIVE_HORIZON
    return PredictionExplanationResponse.model_validate(payload)


@router.get("", response_model=list[TopPredictionResponse])
async def get_top_predictions(
    horizon: str = Query(default="1d", pattern="^(1d|1w|1m)$"),
    direction: str | None = Query(default=None, pattern="^(up|neutral|down)$"),
    confidence_min: int | None = Query(default=None, ge=0, le=100),
    expected_return_min: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[TopPredictionResponse]:
    """Get top predictions across all stocks."""
    _require_supported_horizon(horizon)
    prediction_repo = PredictionRepository(session)
    predictions = await prediction_repo.get_top_predictions(
        horizon=horizon,
        direction=direction,
        confidence_min=confidence_min,
        expected_return_min=Decimal(str(expected_return_min)) if expected_return_min else None,
        limit=limit,
    )

    results = []
    for pred in predictions:
        inst = pred.instrument
        dir_val = pred.predicted_direction.value if hasattr(pred.predicted_direction, 'value') else str(pred.predicted_direction)
        price = pred.features_snapshot.get("price", 0) if isinstance(pred.features_snapshot, dict) else 0
        change_pct = pred.features_snapshot.get("change_percent", 0) if isinstance(pred.features_snapshot, dict) else 0
        try:
            max_prob = max(float(pred.up_probability), float(pred.neutral_probability), float(pred.down_probability))
            no_edge = max_prob < NO_EDGE_THRESHOLD
        except Exception:
            no_edge = False
        results.append(TopPredictionResponse(
            symbol=inst.symbol if inst else "UNKNOWN",
            name=inst.name if inst else "",
            exchange=inst.exchange.code if inst and inst.exchange else "",
            price=Decimal(str(price)),
            change_percent=Decimal(str(change_pct)),
            direction=dir_val,
            probabilities={
                "up": float(pred.up_probability),
                "neutral": float(pred.neutral_probability),
                "down": float(pred.down_probability),
            },
            expected_return=pred.expected_return,
            confidence=pred.confidence,
            horizon=pred.horizon,
            no_clear_edge=no_edge,
            model_horizon=MODEL_NATIVE_HORIZON,
            prediction_timestamp=pred.prediction_timestamp,
            model_version=getattr(pred.model_version, "version", None),
        ))

    return results
